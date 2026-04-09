# Architecture Notes

## Runtime Entry Point

- `app/fusball.py` is the canonical entrypoint and delegates to legacy startup.
- `app/lcars.py` remains as a compatibility entrypoint during migration.
- `app/ui/ui.py` owns the Pygame lifecycle, event loop, and screen transitions.

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
- A plain text audit trail is appended to `logfile.log`.

## Known Legacy Constraints

- Storage format is legacy shelve files (`.bak/.dir` style artifacts exist in repo).
- Relative file paths assume process cwd is `app/` when launching `fusball.py`.
- UI was built for kiosk/touchscreen/fullscreen operation.
