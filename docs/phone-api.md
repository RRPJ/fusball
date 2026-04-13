# Phone API Reference

This document is the endpoint-level reference for the mobile API flow in `app/phone_api.py`.

The repository now has two runtime flows:

- touch-screen kiosk flow: fullscreen local Pygame UI
- mobile API flow: browser-based phone interface and JSON API

The mobile API flow is the preferred modern operator path. This document covers only that flow.

## Base Path

- Default host/port: `http://<host>:8080`
- Mobile page: `GET /phone`

## Authentication

Write endpoints require the operator token header:

- Header: `X-Operator-Token`
- Env var used by server: `FUSBALL_PHONE_API_TOKEN`
- If token is not configured, write endpoints return `503`.

## Environment Configuration

- `FUSBALL_PHONE_API_TOKEN`: operator token for write requests.
- `FUSBALL_PHONE_API_DB_DIR`: data directory override (`playerdb`, `recentplayers`, `tagdb`, `match_history`, `logfile.log`).

## Endpoint Summary

### Health

- `GET /api/health`
- Returns: `{ "ok": true }`

### Leaderboard

- `GET /api/leaderboard?limit=50&scope=all`
- Query params:
  - `limit` (1-200)
  - `scope`: `all`, `this_month`, `this_week`
- Returns:
  - `count`
  - `items[]` with `position`, `name`, `rank`, `level`, offense/defense stats

### Players

- `GET /api/players`
  - Returns display names (`Alice`, `Bob`, ...)
- `POST /api/players`
  - Auth required
  - Body: `{ "name": "Rutger" }`
  - Creates player with default offense/defense ratings

### Presence (session-scoped)

- `GET /api/presence`
  - Returns active/present players for current API process
- `POST /api/presence`
  - Body: `{ "name": "alice", "active": true }`
- `POST /api/presence/clear`
  - Clears active list

Notes:
- Presence is not persisted across API restarts.

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
- `GET /api/stats?scope=all|this_month|this_week`
- `GET /api/player/<name>/history?n=10`

### Match Submit

- `POST /api/matches`
- Auth required
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

## Common Status Codes

- `200 OK`: read success
- `201 Created`: write success
- `400 Bad Request`: validation failure
- `401 Unauthorized`: missing/invalid operator token
- `409 Conflict`: lock contention or duplicate submit
- `500 Internal Server Error`: persistence failure
- `503 Service Unavailable`: write path disabled (token not configured)

## Operational Notes

- Preferred production operation (manual, double-click):
  - `start_phone_api_service.bat`
  - `stop_phone_api_service.bat`
  - `status_phone_api_service.bat`
- Compatibility launcher:
  - `run_phone_api_prod.bat` delegates to production service start behavior.
- Development launcher:
  - `run_phone_api_dev.bat`
- Dev launcher writes to `sandbox/dev-data`.
- Production service start writes to `app/` data, performs startup backup, and runs a watchdog that restarts the API after repeated health failures.
- Production service stop closes the phone API and watchdog processes.

## See Also

- `docs/phone-write-policy.md`
- `docs/development.md`
- `docs/data-safety.md`
- `docs/backlog.md`
