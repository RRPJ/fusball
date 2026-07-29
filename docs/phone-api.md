# Phone API Reference

This document is the endpoint-level reference for the Fusball phone API in `app/phone_api.py`.

The phone API is the repository's primary runtime. It serves both the browser-based operator UI and the JSON endpoints used by phone clients and hosted deployments.

`create_app()` in `app/phone_api.py` remains the composition root, but the UI
markup/CSS/JS live in `app/templates/` and `app/static/` (cache-versioned),
and routes are grouped into focused blueprints under `app/blueprints/`
(`health`, `auth`, `read`, `write`, `admin`). See `docs/architecture.md` for
the full breakdown.

## Base Path

- Default host/port: `http://<host>:8080`
- Mobile page: `GET /phone`
- Managed sign-in page: `GET /login` (strict `clerk` mode only)

## Phone Page Status UX

The `/phone` page exposes request/freshness state directly in the UI so operators can tell the difference between live data, active fetches, and cached fallback.

- Header status card:
  - `Live` means the API is reachable and the page is showing current data.
  - `Fetching ...` means a request is in progress; the card shows the elapsed fetch time.
  - `Snapshot mode` means the API is offline and the page is showing a cached leaderboard snapshot.
- Leaderboard freshness:
  - The leaderboard section shows when standings were last updated.
  - While offline, it shows cached snapshot age instead of implying the data is still live.
- Inline fetch cues:
  - Presence status shows when active players are refreshing and when they were last updated.
  - Odds status shows when matchup odds are being calculated and when the current odds were last updated.

Notes:
- Leaderboard cache is stored in browser `localStorage` with a timestamp.
- Presence remains session-scoped server state and is still lost on API restart.
- Current behavior remains intentionally conservative: the leaderboard refreshes after successful submit and filter changes rather than polling continuously.

## Authentication

Hosted deployments support Clerk-managed individual identity with
application-owned roles in Neon. See `docs/authentication.md`.

- `Authorization: Bearer <session-token>` authenticates a Clerk session.
- `GET /api/auth/me` returns the active user's subject, display name, and role.
- `reader` can access reads, `operator` can also perform existing writes, and
  `admin` is reserved for destructive administration such as match correction.
- `FUSBALL_AUTH_MODE` controls rollout: `legacy`, `hybrid`, or `clerk`.

Phone-page auth navigation:
- Strict `clerk` mode resolves Clerk before initializing operational UI. An
  anonymous `/phone` visit redirects to `/login?next=/phone`; successful
  sign-in redirects back to `/phone`, and sign-out returns to `/login`.
- `/login` validates `next` as a local path and defaults unsafe destinations to
  `/phone`.
- Outside strict `clerk` mode, `/login` redirects to `/phone`.
- `hybrid` mode shows managed login prominently while retaining the PIN
  fallback and existing read-PIN behavior.
- Navigation is presentation-only. Every `/api/*` route still enforces
  authorization server-side regardless of what the client has rendered.

The auth split introduces two headers for the API path:

- Read header: `X-Read-Pin`
- Writer header: `X-Write-Pin`

Access model:

- `GET /api/health` is public (no auth).
- Read endpoints require a valid read PIN or writer PIN.
- Write endpoints require a valid writer PIN.

Legacy compatibility:

- If `WRITE_PIN_HASH` is not configured, write endpoints still accept legacy operator token mode.
- Legacy header: `X-Operator-Token`
- Legacy env var: `FUSBALL_PHONE_API_TOKEN`
- Legacy mode is intended for local compatibility during rollout.

## Environment Configuration

- `FUSBALL_PHONE_API_TOKEN`: operator token for write requests.
- `FUSBALL_PHONE_API_DB_DIR`: data directory override (`playerdb`, `recentplayers`, `match_history`, `logfile.log`).
- `READ_PIN_HASH`: hashed read PIN (`X-Read-Pin`).
- `WRITE_PIN_HASH`: hashed writer PIN (`X-Write-Pin`).

## Endpoint Summary

### Health

- `GET /api/health`
- Returns: `{ "ok": true }`

### Leaderboard

- `GET /api/leaderboard?limit=50&scope=all`
- Query params:
  - `limit` (1-200)
  - `scope`: `all`, `this_quarter`, `this_month`, `this_week`
- Returns:
  - `count`
  - `items[]` with `position`, `name`, `rank`, `level`, offense/defense stats
  - `level` is the average of the offense and defense exposed TrueSkill levels

### Players

- `GET /api/players`
  - Returns display names (`Alice`, `Bob`, ...)
- `POST /api/players`
  - Auth required
  - Body: `{ "name": "Rutger" }`
  - Creates player with default offense/defense ratings

### Presence

- `GET /api/presence`
  - Returns active/present players.
  - Local/shelve mode: process-local, lost on API restart (unchanged
    behavior).
  - Hosted Neon mode: durable, backed by a `player_presence` table with an
    8-hour expiry; expired rows are filtered out of every read
    (`WHERE expires_at > NOW()`), so a crashed/redeployed ephemeral Vercel
    instance cannot leave stale players marked present indefinitely.
- `POST /api/presence`
  - Body: `{ "name": "alice", "active": true }`
  - Marking a player active upserts (refreshes the expiry on hosted Neon);
    marking inactive deletes the row/set entry.
- `POST /api/presence/clear`
  - Clears the active list/table for the resolved store.

Notes:
- `/api/lineup/random` uses the current presence set at request time, so it
  reflects the durable Neon table on hosted deployments and the in-process set
  locally.

### Lineup Helpers

- `POST /api/lineup/random`
  - Body: `{ "mode": "singles" | "doubles" }`
  - Uses active players only
- `POST /api/lineup/auto`
  - Body:
    - `mode` must be `doubles`
    - `selected` must include all 4 slots (`red_defense`, `red_offense`, `blue_offense`, `blue_defense`)
  - Returns balanced slot arrangement using existing match-quality logic

### Match Insights

- `GET /api/odds`
  - Inputs: `red_off`, `blue_off`, optional defenders in doubles
  - Returns probability + ratio text
- `GET /api/h2h?p1=alice&p2=bob`
- `GET /api/team-h2h?team1=alice,bob&team2=carol,dave`
  - Ordered team-vs-team H2H for the current lineup.
  - Team member order is significant for doubles because internal phone-runtime records preserve the gameplay order used by ratings and odds.
  - The phone UI should still render doubles as `Defense + Offense` even though internal arrays remain offense-first.
- `GET /api/stats?scope=all|this_quarter|this_month|this_week`
- `GET /api/player/<name>/profile?scope=all|this_quarter|this_month|this_week&recent_limit=5`
- `GET /api/player/<name>/history?n=10`

### Match Submit

- `POST /api/matches`
- Writer PIN required (`X-Write-Pin`) unless running legacy fallback mode
- Body example:

```json
{
  "team1": ["alice"],
  "team2": ["bob"],
  "score1": 5,
  "score2": 3
}
```

Rules:
- Only finished scores accepted.
- Singles/doubles only; team sizes must be balanced.
- Players must exist already.
- Duplicate submit detection applies in a short time window.

Ordering note:
- Internal gameplay math uses offense-first team arrays for doubles: `[offense, defense]`.
- Phone UI presentation should display doubles as `Defense + Offense`.
- Historical match records written by the phone runtime may therefore be stored offense-first even when shown defense-first in the UI.

### Admin Match Corrections

Match Corrections is a single dedicated admin-only nav entry on `/phone`,
hidden until `GET /api/auth/me` resolves an `admin` role, rather than being
repeated under every Mode/Players/Score/Confirm step.

- `GET /api/admin/matches?limit=30`
  - Requires an active `admin` managed identity.
  - Returns active and voided matches with lifecycle version and audit events.
  - On Neon, audit events for the returned page are loaded in a single
    batched query rather than one query per match.
- `POST /api/admin/matches/<match-id>/void`
- `POST /api/admin/matches/<match-id>/restore`
  - Require an active `admin` managed identity.
  - Require `Idempotency-Key`.
  - Body: `{ "reason": "Incorrect score", "expected_version": 1 }`
  - Return `409 Conflict` for stale versions, repeated state changes, request-key
    reuse, writer contention, or replay-parity failure.

Corrections never delete history. They append an audit event and rebuild
rankings from active history.

## Common Status Codes

- `200 OK`: read success
- `201 Created`: write success
- `400 Bad Request`: validation failure
- `401 Unauthorized`: missing/invalid read credentials on read endpoints
- `403 Forbidden`: missing/invalid writer credentials on write endpoints
- `409 Conflict`: lock contention or duplicate submit
- `500 Internal Server Error`: persistence failure
- `503 Service Unavailable`: write path disabled (legacy mode with no token configured)

## Operational Notes

- Preferred production operation (manual, double-click):
  - `start_phone_api_service.bat`
  - `stop_phone_api_service.bat`
  - `status_phone_api_service.bat`
- Development launcher:
  - `run_phone_api_dev.bat`
- Dev launcher writes to `sandbox/dev-data`.
- Production service start writes to `app/` data, performs startup backup, and runs a watchdog that restarts the API after repeated health failures.
- Production service stop closes the phone API and watchdog processes.

Deployment smoke check:

```bash
python scripts/smoke_phone_api_auth.py --base-url https://<deployment-host> --expect-auth --read-pin <read-pin> --write-pin <write-pin>
```

Recommended deployment model:
- Vercel Production should use production Neon.
- Vercel Preview should use preview Neon.
- Preview deployments should never write into production ranking data.

## See Also

- `docs/phone-write-policy.md`
- `docs/development.md`
- `docs/data-safety.md`
- `docs/backlog.md`
