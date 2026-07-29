# Architecture

## Deployment Model

Fusball has one Flask application with three supported deployment profiles:

- **Production:** Vercel hosts the Flask app through `api/index.py`; Neon
  PostgreSQL is authoritative; `FUSBALL_AUTH_MODE=clerk` enforces Clerk
  identity and Neon-owned application roles.
- **Preview:** a Vercel Preview deployment uses an isolated Neon preview
  branch/project and matching Clerk configuration. It must never point at
  production Neon.
- **Local development:** the app uses the shelve adapter under `app/` (or
  `FUSBALL_PHONE_API_DB_DIR`) unless `DATABASE_URL` is supplied. Legacy
  PIN/token auth is retained for local and rollback compatibility. Developers
  may also configure Neon and Clerk locally for cloud-like testing.

The default auth-mode value in the Python entrypoints is `legacy` for
compatibility. Production is strict only when its environment explicitly sets
`FUSBALL_AUTH_MODE=clerk`.

## Runtime Entry And Composition

- `app/phone_api.py:create_app()` is the composition root.
- `api/index.py` constructs that same app from environment variables and
  exports `app` for Vercel.
- `vercel.json` routes every hosted request to `api/index.py`.
- `app/phone_api.py:main()` runs the same application locally on port `8080`.
- `app/startup.py` contains local runtime diagnostics.

`create_app()` selects the persistence adapter, builds authentication and
request dependencies, registers the route blueprints, and renders the browser
pages. Supplying `DATABASE_URL` selects `NeonWriteStore`; otherwise it selects
`ShelveWriteStore`. A hosted deployment without `DATABASE_URL` would therefore
fall back to ephemeral local files and is not a supported production
configuration.

## Browser UI And Static Assets

The phone UI is not embedded in Python:

- `app/templates/phone.html` renders `/phone`.
- `app/templates/login.html` renders `/login` in strict Clerk mode.
- `app/static/css/phone.css` contains the UI styles.
- `app/static/js/phone.js` contains phone workflow and API behavior.
- `app/static/js/login.js` contains the Clerk sign-in flow.

At app startup, `create_app()` derives a short SHA-256 asset version from the
CSS and JavaScript bytes. Templates append it as `?v=` to asset URLs for
cache-safe deployments.

## Blueprint Boundaries

Routes under `app/blueprints/` are registered by `create_app()`:

- `health.py`: public `GET /api/health`.
- `auth.py`: managed-identity introspection at `GET /api/auth/me`.
- `read.py`: leaderboard, players, presence, odds, H2H, stats, profiles, and
  rating history.
- `write.py`: presence changes, lineup helpers, player creation, and match
  submission.
- `admin.py`: admin match listing and void/restore lifecycle corrections.

Each module exposes a `create_<name>_blueprint(ctx)` factory. The shared
`PhoneApiContext` in `app/services/phone_request_context.py` supplies store
resolution, authorization checks, and local lock helpers without blueprints
importing the composition root.

## Authentication And Authorization

In hosted production, Clerk verifies the session and Neon remains the
authorization authority. `NeonUserRoleStore` resolves only active `app_users`
rows by immutable Clerk subject.

| Role | Permissions |
| --- | --- |
| `reader` | Read API routes |
| `operator` | Reader permissions plus presence, lineup, player, and match writes |
| `admin` | Operator permissions plus match lifecycle administration |

Auth modes are:

- `legacy`: PIN/token behavior only.
- `hybrid`: managed identity first, with configured PIN/token fallback when no
  managed actor resolves.
- `clerk`: Clerk-only; legacy credential headers are ignored.

`/phone`, `/login`, and static assets are browser resources rather than
authorization boundaries. In strict mode `/phone` initially renders the Clerk
bootstrap state; client JavaScript redirects an anonymous visitor to
`/login?next=/phone`. `/login` accepts only a safe local `next` path. All API
authorization is enforced again on the server. `GET /api/health` remains
public.

Admin routes always require a managed actor with the `admin` role; a legacy
shared credential does not grant match-correction access.

## Persistence

### Hosted Neon

Neon is authoritative for hosted production and preview deployments. Ordered,
checksummed migrations under `scripts/sql/migrations/` create and evolve:

- `players` and `recent_players`
- `match_history`
- `app_users`
- `match_events` and `rating_baselines`
- `player_presence`
- `schema_migrations`

Active history drives rankings and analytics. Match records have `active` or
`voided` lifecycle state and an optimistic `version`. `match_events` retain
actor-attributed submit, void, and restore events. `rating_baselines` provide
the trusted starting point for deterministic replay. Voided matches remain in
history but are excluded from normal ranking and analytics reads.

Hosted presence is durable across Vercel instances. `player_presence` rows
expire after eight hours; reads include only `expires_at > NOW()`. Marking a
player active upserts and refreshes the expiry, while marking inactive deletes
the row.

### Local Shelve Compatibility

Without `DATABASE_URL`, local state is stored in the configured data directory:

- `playerdb*`: materialized offense/defense ratings
- `recentplayers*`: recent-player ordering
- `match_history*`: structured match records
- `match_events*` and `rating_baselines*`: lifecycle replay state
- `logfile.log`: legacy text audit/debug trail

Local presence is intentionally an in-process set owned by the store instance
and is lost when the server restarts. Shelve is supported for local
development and compatibility; it is not a hosted failover for Neon.

## Write Consistency And Idempotency

Neon rating/history writes use database transactions. Match submit and
void/restore acquire the same PostgreSQL transaction advisory lock to serialize
rating replay, and match submit also locks participating player rows. A supplied
match `Idempotency-Key` is stored uniquely and replays the original result.
Admin correction keys are mandatory, and corrections additionally enforce the
expected lifecycle version, verify replay parity, update lifecycle state,
append an event, and rematerialize ratings atomically.

The local shelve adapter uses `phone_api_write.lock` around player creation,
match submit, and admin correction. Match requests without an idempotency key
also use a 60-second process-local signature check as an accidental-repeat
fallback. Supplied keys are checked against local history, but the file lock
and in-memory duplicate tracker are local-process mechanisms rather than
hosted concurrency guarantees.

## Readiness

`GET /api/health` is a readiness endpoint, not only a process liveness check:

- Shelve readiness verifies that the data directory is usable and that the
  current player store can be read when present.
- Neon readiness verifies database connectivity, required tables, and the
  exact ordered migration manifest recorded in `schema_migrations`.

It returns `200` with `{"ok": true}` when ready. An unavailable store,
unreachable database, missing table, or incompatible migration state returns
`503` with a non-secret reason.

## Ranking And Team Ordering

TrueSkill tracks separate offense and defense ratings. Player level is the
average of the exposed offense and defense levels.

Internal doubles arrays are offense-first:

```text
[offense, defense]
```

The phone UI displays doubles in human-facing table order:

```text
Defense + Offense
```

Submission, odds, history, H2H, replay, and presentation code must preserve
that distinction.

## Core Services

- `app/services/match_service.py`: odds, rating updates, lineup balancing
- `app/services/match_history.py`: history queries and deterministic replay
- `app/services/match_log.py`: local text log
- `app/services/phone_write_store.py`: Neon and shelve adapters
- `app/services/store_contracts.py`: shared persistence interfaces
- `app/services/auth.py`: Clerk verification and Neon role resolution
- `app/services/neon_migrations.py`: ordered migration runner
- `app/services/neon_data_safety.py`: readiness, integrity, export, and restore
- `app/services/phone_validation.py`: request validation and duplicate fallback
- `app/services/leaderboard.py`: leaderboard shaping

## See Also

- [Authentication](authentication.md)
- [Data safety](data-safety.md)
- [Development](development.md)
- [Phone API](phone-api.md)
- [Phone write policy](phone-write-policy.md)
