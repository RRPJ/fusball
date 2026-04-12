# Architecture Notes

## Runtime Model

The repository supports two runtime flows over the same ranking and persistence layer:

- Touch-screen kiosk flow:
  - fullscreen local Pygame UI on the host machine
  - canonical entrypoint: `app/fusball.py`
- Mobile API flow:
  - phone-oriented web/API layer in `app/phone_api.py`
  - preferred modern operator flow for day-to-day use

The kiosk flow remains supported for dedicated touch installations, but the mobile API flow is now the preferred operator experience when phone access is available.

## Runtime Entry Point

- `app/fusball.py` is the canonical entrypoint and delegates to legacy startup.
- `app/lcars.py` remains as a compatibility entrypoint during migration.
- `app/ui/ui.py` owns the Pygame lifecycle, event loop, and screen transitions.
- `app/phone_api.py` owns the browser-based phone UI and JSON API runtime.

## Screen System

- Screens are under `app/screens/` and inherit from `LcarsScreen`.
- The main menu is `ScreenMain` and links to workflows:
  - Enter match (`ScreenEnterMatch`)
  - Enter outcome (`ScreenEnterOutcome`)
  - Log view (`ScreenLog`)
  - Power screen

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
  - `tagdb`: badge/tag to player mapping
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

- `app/datasources/`: external/network data adapters
- `scripts/`: operational utilities (backup, inspect, sandbox refresh, smoke)
- repo-root `test_*.py`: regression and API behavior tests

## See Also

- `docs/development.md`
- `docs/data-safety.md`
- `docs/phone-api.md`
- `docs/backlog.md`

## Known Legacy Constraints

- Storage format is legacy shelve files (`.bak/.dir` style artifacts exist in repo).
- Relative file paths assume process cwd is `app/` when launching `fusball.py`.
- UI was built for kiosk/touchscreen/fullscreen operation.
