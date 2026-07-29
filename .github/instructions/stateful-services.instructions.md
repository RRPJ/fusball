---
applyTo: "app/services/**/*.py,app/dbmigration.py,scripts/migrate_neon_schema.py,scripts/migrate_shelve_to_neon.py,scripts/check_neon_integrity.py,scripts/export_neon_backup.py,scripts/restore_neon_backup.py,scripts/sql/migrations/*.sql,test_match_flow.py,test_integration.py,test_neon_*.py"
description: "Use for ranking, shelve/Neon persistence, migrations, integrity, export, or restore work."
---

# Stateful Service Instructions

- Read `docs/architecture.md` and `docs/data-safety.md` before changing persistence, migration, integrity, export, or restore behavior.
- Hosted production uses Neon as the authoritative store. Local development and legacy compatibility use shelve under `app/` or `FUSBALL_PHONE_API_DB_DIR`.
- Treat `app/playerdb*`, `app/recentplayers*`, `app/match_history*`, `app/match_events*`, and `app/rating_baselines*` as valuable local/legacy state. Run `python scripts/backup_state.py` before changing local persistence logic, schema assumptions, or shelve migration behavior, and separately preserve the lifecycle shelves because the script does not currently copy them.
- Preserve offense/defense ratings separately and preserve offense-first `[offense, defense]` internal team ordering.
- Hosted writes must preserve transaction atomicity, the transaction-scoped advisory lock, row locking, persisted idempotency, actor attribution, lifecycle audit events, and deterministic replay parity.
- Local writes must preserve `phone_api_write.lock`, `409 Conflict` behavior, additive shelve compatibility, and the 60-second process-local duplicate fallback when no idempotency key is supplied.
- Hosted presence is stored in `player_presence` with an eight-hour expiry; local shelve presence remains process-local.
- Add hosted schema changes as ordered, checksum-verified files under `scripts/sql/migrations/`. Never edit or renumber an applied migration; document forward and rollback impact.
- Before applying a migration, run `python scripts/migrate_neon_schema.py` to inspect the ordered manifest. Apply and verify only against an explicitly selected target.
- Neon-sensitive work requires the relevant `test_neon_store.py`, `test_neon_migrations.py`, and `test_neon_data_safety.py` coverage plus `python scripts/check_neon_integrity.py` where a database is available.
- Migration/cutover work should also verify `python scripts/smoke_neon_parity.py`; recovery changes require encrypted export and an isolated Preview/restore-drill restore. Never restore into production.
- Keep persistence diffs small and update `docs/data-safety.md` whenever backup, migration, integrity, rollback, or restore expectations change.
