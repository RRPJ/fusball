# Contributing

## Development Flow

1. Create a branch and follow [docs/development.md](docs/development.md).
2. Choose the correct mode: local shelve, explicitly configured cloud-like Neon/Clerk, or isolated Vercel Preview.
3. Keep changes small and behavior-preserving unless gameplay or an API contract is intentionally changing.
4. Run the smallest relevant checks, then the CI-equivalent matrix before opening a high-risk PR.

Never point local experiments, Vercel Preview, migration tests, or restore drills at production Neon.

## Communication Expectation

- Explain what changed, why, validation performed, and known trade-offs.
- Describe production behavior as Vercel + Neon + strict Clerk; label shelve and legacy PIN/token paths as local or rollback compatibility.
- Update maintainers' documentation when configuration, auth, write, migration, deployment, or recovery behavior changes.

## Coding Standards

- Use `docs/development.md` as the source of truth for setup, lint, format, and pre-commit commands.
- Preserve offense-first internal rating/team ordering even though the phone UI displays doubles as Defense + Offense.
- Add concise docstrings only when a changed function's intent is not immediately obvious.

## Data Safety Requirements

- Run `python scripts/backup_state.py` before changing local persistence logic or data-shape assumptions, and separately preserve `match_events*` and `rating_baselines*` because the script does not currently copy those lifecycle shelves.
- Put hosted schema changes in ordered, checksum-verified files under `scripts/sql/migrations/`; never rewrite an applied migration.
- Document migration, integrity, encrypted-export, isolated-restore, rollback, and rollout impact in [docs/data-safety.md](docs/data-safety.md).
- Verify Neon-sensitive changes against an isolated database with the relevant migration, store, integrity, parity, export, and restore-drill checks.

## Automated Checks

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs:

- Ruff and Black on Python 3.11.
- `python scripts/smoke_check.py` plus `test_phone_api.py`, `test_match_flow.py`, `test_integration.py`, `test_neon_store.py`, `test_neon_migrations.py`, `test_neon_data_safety.py`, and `test_auth.py` on Python 3.11 and 3.14.
- `test_neon_store.py` against PostgreSQL 17 on Python 3.11 to verify transaction rollback behavior.

## Pull Request Checklist

- [ ] Relevant targeted tests pass.
- [ ] Full smoke/regression matrix passes for cross-cutting changes.
- [ ] Ruff and Black checks pass.
- [ ] Auth, role, locking, idempotency, replay, presence, and readiness behavior remain correct where affected.
- [ ] Local shelve changes have a backup and compatibility/rollback notes.
- [ ] Neon changes use ordered migrations and include integrity plus isolated restore-readiness evidence.
- [ ] README/docs reflect behavior, configuration, deployment, or recovery changes.
