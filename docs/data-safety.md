# Data Safety And Migration

This project stores operational data in Python shelve files. Treat these files as stateful assets.

## Before Any Refactor Or Dependency Upgrade

1. Stop the app.
2. Copy all shelve-related files from `app/` to a timestamped backup folder.
3. Copy `app/logfile.log` if present.
4. If phone API is in use, also back up `app/match_history*` and confirm whether writes were targeting `app/` or `sandbox/dev-data`.

Example backup layout:

- `backups/2026-04-09/playerdb*`
- `backups/2026-04-09/recentplayers*`
- `backups/2026-04-09/match_history*`
- `backups/2026-04-09/logfile.log`

Historical kiosk-only files may still exist in older backups. Keep them for archive purposes, but they are no longer part of the active runtime contract.

## Compatibility Caveat

Shelve backend formats are platform-dependent. Files created on one OS/Python build may not always be readable on another.

Recommended policy:
- Keep one canonical runtime environment for production data.
- Use exported snapshots (for example JSON) for cross-platform migration work.

## Existing Migration Helper

- `app/dbmigration.py` upgrades old player records from single-rating to offense/defense tuple format.
- Run it from the `app/` directory after creating a backup.

## Neon Parity Verification

After running shelve -> Neon import, verify parity before any cutover:

```bash
python scripts/smoke_neon_parity.py --db-dir app --database-url <database-url> --mode strict
```

Notes:
- `--mode strict` compares players, recent player ordering, and match-history IDs.
- Use `--mode counts` for a faster count-only comparison.

For the full deployment sequence, see `docs/priority-0-cutover-runbook.md`.

## Restore Procedure (Rollback)

Use this when data corruption or a failed migration is suspected.

1. Stop phone API processes.
2. Identify the target backup folder under `backups/<timestamp>/`.
3. Copy backup artifacts back into `app/` for each relevant store:
	- `playerdb*`
	- `recentplayers*`
	- `match_history*` (if present)
	- `logfile.log` (optional legacy audit restore)
4. Start app from `app/` and run smoke validation:
	- `python scripts/smoke_check.py`
5. Run targeted API/unit checks if phone write path was involved:
	- `python -m unittest test_phone_api.py`
6. Manually verify leaderboard and one match flow before reopening normal use.

Rollback decision note:
- If smoke/tests fail after restore, stop and restore from an earlier known-good snapshot.
- Do not run migrations repeatedly against uncertain state; re-back up first.

## See Also

- `docs/development.md`
- `docs/architecture.md`
- `docs/backlog.md`

## Suggested Next Improvement

Add a dedicated export/import utility (`scripts/export_playerdb.py`, `scripts/import_playerdb.py`) to decouple persistent data from shelve backend internals.
