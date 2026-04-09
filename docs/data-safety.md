# Data Safety And Migration

This project stores operational data in Python shelve files. Treat these files as stateful assets.

## Before Any Refactor Or Dependency Upgrade

1. Stop the app.
2. Copy all shelve-related files from `app/` to a timestamped backup folder.
3. Copy `app/logfile.log` if present.

Example backup layout:

- `backups/2026-04-09/playerdb*`
- `backups/2026-04-09/recentplayers*`
- `backups/2026-04-09/tagdb*`
- `backups/2026-04-09/logfile.log`

## Compatibility Caveat

Shelve backend formats are platform-dependent. Files created on one OS/Python build may not always be readable on another.

Recommended policy:
- Keep one canonical runtime environment for production data.
- Use exported snapshots (for example JSON) for cross-platform migration work.

## Existing Migration Helper

- `app/dbmigration.py` upgrades old player records from single-rating to offense/defense tuple format.
- Run it from the `app/` directory after creating a backup.

## Suggested Next Improvement

Add a dedicated export/import utility (`scripts/export_playerdb.py`, `scripts/import_playerdb.py`) to decouple persistent data from shelve backend internals.
