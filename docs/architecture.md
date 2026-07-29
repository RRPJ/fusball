# Architecture Notes

## Runtime Model

The repository supports one runtime flow over the ranking and persistence layer:

- Phone API flow:
  - browser-based phone UI and JSON API in `app/phone_api.py`
  - primary operator entrypoint for local service mode and hosted deployments

## Runtime Entry Point

- `app/phone_api.py` owns the browser-based phone UI and JSON API runtime.
- `api/index.py` exposes the same app factory for Vercel deployments.
- `app/startup.py` contains phone-runtime diagnostics for data-directory access.

## Request Surface

- `/phone` renders the operator UI.
- `/api/*` provides health, leaderboard, player, presence, lineup, odds, stats, history, and match-submit endpoints.
- `start_phone_api_service.bat` and related PowerShell scripts provide the supported Windows production lifecycle.

## Phone Runtime Composition

`app/phone_api.py` stays the composition root (`create_app()`), but the
runtime is decomposed rather than monolithic:

- **Templates/static assets**: the phone UI markup, CSS, and JS no longer live
  as an embedded Python string. They live in `app/templates/phone.html`,
  `app/static/css/phone.css`, and `app/static/js/phone.js`, served through
  Flask's default template/static handling. `create_app()` computes a short
  SHA-256-derived `asset_version` from the CSS/JS bytes at startup and appends
  it as a `?v=` query string on both asset URLs for cache-safe versioning
  (no manual version bump required).
- **Blueprints**: routes are split into focused Flask blueprints under
  `app/blueprints/`:
  - `health.py`: `GET /api/health` (always public).
  - `auth.py`: `GET /api/auth/me` (managed-identity introspection).
  - `read.py`: leaderboard, players, presence GET, odds, H2H, stats, profile,
    history reads.
  - `write.py`: presence set/clear, lineup random/auto, player create, match
    submit.
  - `admin.py`: `GET /api/admin/matches` and the void/restore lifecycle
    endpoints (admin-only).
  - Each blueprint module exposes a `create_<name>_blueprint(ctx)` factory
    that closes over a shared `PhoneApiContext` instead of importing global
    state, so blueprints have no circular import dependency on
    `app/phone_api.py`.
- **Shared request context**: `app/services/phone_request_context.py` defines
  `PhoneApiContext`, a small dataclass carrying the auth/store/lock
  dependencies each blueprint needs (authenticator, store resolver, write-lock
  helpers, auth-mode/Clerk config, admin-access check). `create_app()` builds
  one `PhoneApiContext` and passes it to every blueprint factory.
- **Extracted services**: `app/services/phone_validation.py` (request-payload
  validation, duplicate-submit tracking) and `app/services/leaderboard.py`
  (leaderboard row shaping) hold logic that previously lived as private
  helpers inside `phone_api.py`.

## Phone Auth UX

- Strict `clerk` mode hides the operational app content (`#appContent`,
  `#stickyBar`) behind `display:none` until the Clerk session resolves, so
  managed sign-in is visible immediately at page load rather than only at the
  Confirm step. Static assets and `GET /api/health` remain reachable
  regardless of auth state — the gating is client-side presentation only;
  every `/api/*` write and admin route still enforces authorization
  server-side.
- `hybrid` mode shows the managed login prominently while still offering the
  PIN fallback and existing read-PIN behavior.
- Match Corrections is a single dedicated admin-only nav entry
  (`#adminNavBtn` / the admin view), hidden until `GET /api/auth/me` resolves
  an `admin` role, instead of being repeated under every Mode/Players/
  Score/Confirm step.

## Presence Semantics

- Local/shelve deployments keep in-process presence semantics: `ShelveWriteStore`
  tracks an in-memory `set` scoped to the store instance's lifetime (same
  behavior as before this refactor).
- Hosted Neon deployments now have durable presence: `NeonWriteStore` persists
  presence in a `player_presence` table (migration `0005_player_presence.sql`)
  with an 8-hour expiry (`PRESENCE_TTL_SECONDS`). Reads filter
  `WHERE expires_at > NOW()`, so stale rows from crashed/redeployed ephemeral
  Vercel instances self-expire without a background sweeper. `set_presence`
  upserts (refreshing the expiry) or deletes; `clear_presence` truncates the
  table. This replaces the previous purely in-memory closure variable, which
  was silently broken across ephemeral hosted instances.
- Both adapters implement a shared `PresenceRepository` contract in
  `app/services/store_contracts.py` (`list_active_presence`, `set_presence`,
  `clear_presence`), used by the `read`/`write` blueprints instead of a bare
  context field.

## Ranking And Odds

- `app/odds.py` provides:
  - Win probability calculation (`win_probability`)
  - Player exposure level (`playerLevel`), defined as the average of offense and defense exposed ratings
  - Rank string calculation (`findRank`)
- TrueSkill is used with offense and defense tracked separately per player.

## Persistence

- Neon PostgreSQL is authoritative for hosted Vercel deployments.
- Python `shelve` remains the supported local-development compatibility store.
- Local stores:
  - `playerdb`: player ratings and leaderboard source
  - `recentplayers`: recent player names for entry UX
  - `match_history`: structured match records for analytics/history replay
- A plain text audit trail is appended to `logfile.log` for legacy/debug continuity.
- `app/services/store_contracts.py` defines focused player, history, and match
  write contracts shared by both adapters.
- `app/services/domain_models.py` defines shared rating and match payload types.
- Ordered Neon schema changes live under `scripts/sql/migrations/` and are
  recorded with checksums in `schema_migrations`.

Structured match-history record shape includes:
- Timestamp and source marker
- Teams, winner, and final score
- Per-player before/after offense and defense ratings

Match history has separate lifecycle state (`active` or `voided`). Append-only
`match_events` attribute submit/void/restore operations, while
`rating_baselines` provide the trusted starting point for deterministic replay.
Normal ranking and analytics reads exclude non-active records.

## Service Layer

Core domain services live under `app/services/`:

- `match_service.py`: odds, rating updates, lineup balancing
- `match_history.py`: structured match-history append/query/replay helpers
- `match_log.py`: legacy text audit log append
- `phone_write_store.py`: shelve and Neon persistence adapters, including the
  `PresenceRepository` implementations described above. `NeonWriteStore.
  list_match_lifecycle()` batch-loads audit events for every returned match in
  one `WHERE match_id = ANY(%s)` query instead of one query per match, using
  the existing `ix_match_events_match_created` index from migration
  `0003_match_lifecycle.sql`.
- `store_contracts.py`: persistence interfaces (`PlayerRepository`,
  `HistoryRepository`, `MatchWriter`, `PresenceRepository`)
- `neon_migrations.py`: ordered schema migration runner
- `player_store.py`: ranking helpers (`ranked_players`, `rank_labels_by_name`)
  used by leaderboard rendering
- `phone_validation.py`: phone-API request payload validation and duplicate-
  submit tracking, shared by the `write` blueprint
- `leaderboard.py`: leaderboard row shaping shared by the `read` blueprint and
  the `/phone` template render
- `phone_request_context.py`: `PhoneApiContext`, the typed dependency bundle
  shared by all phone-API blueprints

Support modules:

- `scripts/`: operational utilities (backup, inspect, sandbox refresh, smoke)
- repo-root `test_*.py`: regression and API behavior tests

## See Also

- `docs/development.md`
- `docs/data-safety.md`
- `docs/phone-api.md`
- `docs/backlog.md`

## Current Constraints

- Storage format is still legacy shelve for local mode (`.bak/.dir` style artifacts may exist in backups).
- Local service scripts assume app data lives under `app/` unless `FUSBALL_PHONE_API_DB_DIR` overrides it.
- Hosted deployments require Neon-backed persistence; local shelve is not a
  hosted failover mechanism.
- `app/services/player_store.py`'s old CWD-relative shelve helpers
  (`player_names`, `player_exists`, `add_player_if_missing`,
  `ensure_recent_players_initialized`, `recent_player_names`,
  `add_recent_player`) were removed as dead/unsafe code: nothing referenced
  them, and they bypassed the `db_dir`-scoped stores in
  `phone_write_store.py`. `ranked_players`/`rank_labels_by_name` remain and
  are still used by leaderboard rendering. `app/dbmigration.py` is a separate,
  still-documented local shelve data-format upgrade tool (see
  `docs/data-safety.md`) and was intentionally left in place.
