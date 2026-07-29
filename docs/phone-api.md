# Phone API Reference

The Fusball Flask application serves the browser UI and JSON API from the same
runtime. `app/phone_api.py:create_app()` is the composition root;
`api/index.py` exports the app for Vercel. Route implementations live under
`app/blueprints/`, while page templates and assets live under
`app/templates/` and `app/static/`.

## Deployment Profiles

- **Production:** Vercel + authoritative Neon + strict Clerk
  (`FUSBALL_AUTH_MODE=clerk`).
- **Preview:** Vercel Preview + isolated Neon preview data + matching Clerk
  configuration.
- **Local development:** shelve under `app/` or
  `FUSBALL_PHONE_API_DB_DIR`, normally with legacy PIN/token compatibility.
  Local development can instead use Neon and Clerk when explicitly configured.

The code defaults to `legacy` auth mode for compatibility. Production must set
`FUSBALL_AUTH_MODE=clerk`; it must not rely on the default.

## Browser Routes

- `GET /` redirects to `/phone`.
- `GET /phone` renders the operator UI.
- `GET /login` renders the Clerk sign-in page only in strict `clerk` mode. In
  other modes it redirects to `/phone`.
- `GET /static/*` serves versioned CSS and JavaScript assets.

In strict mode `/phone` initially renders a Clerk bootstrap state. Browser
JavaScript resolves the session and redirects an anonymous visitor to
`/login?next=/phone`. The `/login` route accepts only a local `next` path and
falls back to `/phone` for unsafe values. This browser flow is not an
authorization boundary; API routes enforce access server-side.

## Authentication

### Production Clerk Contract

Hosted production uses a Clerk session token:

```http
Authorization: Bearer <Clerk session token>
```

The backend verifies the Clerk session and authorized party, then resolves the
immutable Clerk subject against an active row in Neon's `app_users` table.
Unknown or disabled users are not authorized.

| Role | API access |
| --- | --- |
| `reader` | Read endpoints |
| `operator` | Reads plus presence, lineup, player, and match writes |
| `admin` | Operator access plus match listing and void/restore |

`GET /api/auth/me` returns the resolved `subject`, `display_name`, and `role`.
Admin routes require a managed `admin` actor even in `legacy` or `hybrid`
deployments; a PIN or shared token cannot authorize corrections.

### Compatibility Modes

`FUSBALL_AUTH_MODE` accepts:

- `legacy`: managed authentication is disabled. Reads may use `X-Read-Pin` or
  `X-Write-Pin`; writes use `X-Write-Pin`, or `X-Operator-Token` when no writer
  PIN hash is configured.
- `hybrid`: a managed actor is used when present; otherwise the configured
  legacy PIN/token checks remain available.
- `clerk`: managed identity only. `X-Read-Pin`, `X-Write-Pin`, and
  `X-Operator-Token` are ignored for authorization.

In non-strict modes, reads are open when neither read nor writer PIN hashes are
configured. If `WRITE_PIN_HASH` is configured, write requests require
`X-Write-Pin`. If it is absent, writes fall back to `X-Operator-Token` matched
against `FUSBALL_PHONE_API_TOKEN`; without either write configuration, writes
return `503`.

## Environment Configuration

### Hosted Production And Preview

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Selects authoritative Neon storage |
| `FUSBALL_AUTH_MODE` | Set to `clerk` for production |
| `CLERK_SECRET_KEY` | Backend session verification |
| `CLERK_PUBLISHABLE_KEY` | Browser Clerk integration; also used to derive the frontend origin |
| `CLERK_AUTHORIZED_PARTIES` | Comma-separated exact allowed frontend origins |
| `CLERK_FRONTEND_API_URL` | Optional frontend-origin compatibility fallback |

Preview must use preview-specific Neon and Clerk values and must never point at
production ranking data.

### Local And Rollback Compatibility

| Variable | Purpose |
| --- | --- |
| `FUSBALL_PHONE_API_DB_DIR` | Shelve/log data-directory override |
| `READ_PIN_HASH` | Werkzeug-compatible hash for `X-Read-Pin` |
| `WRITE_PIN_HASH` | Werkzeug-compatible hash for `X-Write-Pin` |
| `FUSBALL_PHONE_API_TOKEN` | Shared `X-Operator-Token` value when no writer PIN is configured |
| `FUSBALL_AUTH_MODE` | `legacy`, `hybrid`, or `clerk` |

Operational backup/restore tooling additionally uses `FUSBALL_BACKUP_KEY` and
`RESTORE_DATABASE_URL`; those variables are not consumed by API request
handling.

## Readiness

### `GET /api/health`

Public readiness endpoint.

- `200`: `{"ok": true}` when the selected store is ready.
- `503`: store resolution failed or readiness failed.

Shelve readiness checks the configured data directory and reads the current
player store when present. Neon readiness checks connectivity, all required
tables, and an exact match between the applied `schema_migrations` rows and the
ordered migration manifest. Failure responses expose a reason such as
`store_unavailable`, `database_unavailable`, or `schema_incompatible`, without
including connection details.

## Identity

### `GET /api/auth/me`

Requires a valid managed Clerk identity.

```json
{
  "subject": "user_...",
  "display_name": "Operator Name",
  "role": "operator"
}
```

Returns `401` when no active managed actor resolves. Legacy credentials do not
make this endpoint return an identity.

## Read Endpoints

These routes require `reader`, `operator`, or `admin` in strict Clerk mode.
Compatibility access follows the mode rules above.

### `GET /api/leaderboard`

Query parameters:

- `limit`: clamped to `1`-`200`; default `50`
- `scope`: `all`, `this_quarter`, `this_month`, or `this_week`

Returns `count` and `items`. Each item includes position, display name, rank,
level, and offense/defense values. Level is the average of exposed offense and
defense TrueSkill levels. Invalid scope returns `400`.

### `GET /api/players`

Returns display-cased player names:

```json
{"count": 2, "items": ["Alice", "Bob"]}
```

### `GET /api/presence`

Returns players currently marked active.

- Neon: durable `player_presence` rows whose `expires_at` is later than
  `NOW()`. Rows expire after eight hours.
- Shelve: an in-process set for the lifetime of the server/store instance.

### `GET /api/odds`

Query parameters:

- required: `red_off`, `blue_off`
- doubles: `mode=doubles`, with optional `red_def` and `blue_def` query values

Returns a rounded win `probability` and ratio text. The phone UI supplies both
defenders for doubles. Unknown players return `400`; an empty rating store
returns `503`.

### `GET /api/h2h`

Query parameters: two distinct names in `p1` and `p2`. Invalid input returns
`400`.

### `GET /api/team-h2h`

Query parameters: comma-separated `team1` and `team2`. Both teams must have the
same size, either one or two. Doubles order is significant and remains
offense-first internally.

### `GET /api/stats`

Optional `scope`: `all`, `this_quarter`, `this_month`, or `this_week`.
Invalid scope returns `400`.

### `GET /api/player/<name>/profile`

Query parameters:

- `scope`: `all`, `this_quarter`, `this_month`, or `this_week`
- `recent_limit`: clamped to `1`-`10`; default `5`

### `GET /api/player/<name>/history`

Query parameter `n` is clamped to `1`-`50`; default `10`. Returns rating
snapshots for the normalized player name.

Normal history-derived reads exclude voided matches.

## Operator Endpoints

These routes require `operator` or `admin` in strict Clerk mode.

### `POST /api/presence`

Body:

```json
{"name": "alice", "active": true}
```

The player must exist and `active` must be Boolean. In Neon, activation
upserts and refreshes the eight-hour expiry; deactivation deletes the row.
Locally it updates the process-local set. Success returns `200`.

### `POST /api/presence/clear`

Clears all active presence for the selected store and returns `200`.

### `POST /api/lineup/random`

Body:

```json
{"mode": "singles"}
```

`mode` is `singles` or `doubles`. The route selects from active known players
and returns `400` when too few are present. This is a computation endpoint and
does not persist a match.

### `POST /api/lineup/auto`

Body:

```json
{
  "mode": "doubles",
  "selected": {
    "red_defense": "alice",
    "red_offense": "bob",
    "blue_defense": "carol",
    "blue_offense": "dave"
  }
}
```

Requires four unique existing players and returns a balanced slot assignment.

### `POST /api/players`

Body:

```json
{"name": "Rutger"}
```

Names are normalized to lowercase and pass a 2-30 length check. The current
character rule is `[a-z][a-z\- ]+[a-z]`: letters, spaces, and hyphens, with a
letter at both ends and a practical minimum of three characters. Success
creates default offense and defense ratings and returns `201`. An existing
player returns `409`.

### `POST /api/matches`

Body:

```json
{
  "team1": ["alice"],
  "team2": ["bob"],
  "score1": 5,
  "score2": 3
}
```

Rules:

- balanced singles or doubles only
- every player must already exist
- no player may appear twice
- integer, non-negative scores
- exactly one side must reach `5`

`Idempotency-Key` is optional at the API boundary and is limited to 128
characters. The phone UI always sends a generated key. Hosted clients should
do the same: Neon persists the key uniquely, returns the original result for
the same payload, and rejects reuse for another payload. Without a key, the
runtime has only a 60-second process-local duplicate-signature fallback, which
is not a durable hosted guarantee.

Neon performs rating updates, match history insertion, and submit-event
insertion in one transaction serialized by a PostgreSQL advisory transaction
lock. Local shelve uses `phone_api_write.lock`.

Success returns `201`, including `match_id`, teams, scores, and winner.
Managed submissions persist the Clerk subject; compatibility submissions use
`legacy:shared-credential`.

#### Doubles Ordering

Submitted and stored doubles arrays are offense-first:

```text
[offense, defense]
```

The phone UI displays them as:

```text
Defense + Offense
```

Clients must not reverse arrays before calling odds, team H2H, or match submit.

## Admin Match Corrections

These routes always require a managed actor with the `admin` role.

### `GET /api/admin/matches`

Query parameter `limit` is clamped to `1`-`100`; default `30`. Returns active
and voided matches with lifecycle `status`, `version`, `submitted_by`, and
ordered audit `events`.

### `POST /api/admin/matches/<match-id>/void`

### `POST /api/admin/matches/<match-id>/restore`

Required header:

```http
Idempotency-Key: <unique request ID>
```

Body:

```json
{
  "reason": "Incorrect score",
  "expected_version": 1
}
```

The reason must be 3-500 characters. `expected_version` must be an integer,
and the idempotency key must be non-empty and at most 128 characters.

Corrections never delete the original match. They:

1. verify current replay parity,
2. enforce the expected version and target lifecycle state,
3. update the match to `active` or `voided`,
4. append an actor-attributed `void` or `restore` event, and
5. rebuild materialized ratings from active history.

Neon performs those steps atomically under the same rating-replay advisory
transaction lock used by match submit. The local adapter uses
`phone_api_write.lock`.

Responses:

- `200`: correction applied, or an identical request key replayed
- `400`: malformed body, reason, version, or idempotency key
- `404`: match not found
- `409`: stale version, already-in-target-state request, request-key conflict,
  replay-parity failure, or local lock contention

## Common Status Behavior

| Status | Meaning |
| --- | --- |
| `200` | Successful read, presence/lineup operation, or admin correction |
| `201` | Player created or match submitted/idempotently replayed |
| `400` | Request validation failure; match-key reuse with another payload is also surfaced here |
| `401` | Authentication missing/invalid for reads, strict Clerk writes, admin routes, or legacy token mode |
| `403` | Authenticated managed role lacks permission, or writer PIN authorization fails |
| `404` | Admin lifecycle match ID not found |
| `409` | Duplicate player/submit, local writer contention, or lifecycle conflict |
| `500` | Persistence operation failed |
| `503` | Store/readiness unavailable, empty odds store, or legacy write auth is not configured |

## Phone Page Freshness

The browser UI distinguishes:

- `Live`: current API data
- `Fetching ...`: an active request with elapsed time
- `Snapshot mode`: cached leaderboard from browser `localStorage`

Offline snapshot mode disables match entry. The leaderboard refreshes after
successful submit and filter changes rather than continuously polling.
Presence durability follows the selected store: durable/expiring in Neon and
process-local in shelve.

## Operations

Vercel Production should use production Neon and strict Clerk. Vercel Preview
should use isolated preview Neon and Clerk configuration. `vercel.json` sends
all routes to `api/index.py`.

`run_phone_api_dev.bat` is the local shelve development launcher. The Windows
`start_phone_api_service.bat`, `stop_phone_api_service.bat`, and
`status_phone_api_service.bat` files are historical local wrappers whose
watchdog still probes `/health` instead of `/api/health`; do not use them as
the hosted production lifecycle or as a current readiness-managed launcher.

## See Also

- [Architecture](architecture.md)
- [Authentication](authentication.md)
- [Data safety](data-safety.md)
- [Development](development.md)
- [Phone write policy](phone-write-policy.md)
