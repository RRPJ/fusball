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

## Ranking And Odds

- `app/odds.py` provides:
  - Win probability calculation (`win_probability`)
  - Player exposure level (`playerLevel`)
  - Rank string calculation (`findRank`)
- TrueSkill is used with offense and defense tracked separately per player.

## Persistence

- Primary store is Python `shelve` in the `app/` working directory.
- Observed stores:
  - `playerdb`: player ratings and leaderboard source
  - `recentplayers`: recent player names for entry UX
  - `match_history`: structured match records for analytics/history replay
- A plain text audit trail is appended to `logfile.log` for legacy/debug continuity.

Structured match-history record shape includes:
- Timestamp and source marker
- Teams, winner, and final score
- Per-player before/after offense and defense ratings

## Service Layer

Core domain services live under `app/services/`:

- `match_service.py`: odds, rating updates, lineup balancing
- `match_history.py`: structured match-history append/query/replay helpers
- `match_log.py`: legacy text audit log append
- `player_store.py`: ranking helpers and player list utilities

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
- Hosted deployments are converging on Neon-backed persistence, but local shelve remains the compatibility path today.
