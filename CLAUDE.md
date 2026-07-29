# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with this repository.

## Read First

- `README.md` — project overview, entrypoints, and run modes
- `docs/architecture.md` — runtime, blueprint, asset, and persistence boundaries
- `docs/development.md` — local, cloud-like, and hosted verification workflows
- `docs/authentication.md` — Clerk modes and Neon-owned roles
- `docs/phone-api.md` and `docs/phone-write-policy.md` — endpoint and write contracts
- `docs/data-safety.md` — Neon and local-shelve recovery procedures
- `.github/copilot-instructions.md` — editing and verification rules

## Repository Overview

Fusball is a phone-first foosball match and leaderboard service. It tracks offense and defense skill separately with TrueSkill.

- **Production:** Vercel hosts the Flask app through `api/index.py`; Neon is authoritative; `FUSBALL_AUTH_MODE=clerk` enforces Clerk authentication; active `app_users` rows in Neon grant `reader`, `operator`, or `admin` permissions.
- **Preview:** use an isolated Vercel Preview deployment, matching Neon preview branch/project, and Clerk configuration. Never connect Preview or restore drills to production Neon.
- **Local development:** `app/phone_api.py` can use shelve under `app/` or `FUSBALL_PHONE_API_DB_DIR`. `legacy` PIN/token and `hybrid` fallback modes exist for local compatibility and rollback testing, not as the production standard.

`app/phone_api.py` is the composition root and local launcher. Routes are split across `app/blueprints/`; `/phone` and `/login` templates and browser assets live in `app/templates/` and `app/static/`.

## Quick Commands

```bash
pip install -r requirements-dev.txt

python scripts/smoke_check.py
python -m unittest test_phone_api.py test_match_flow.py test_integration.py test_neon_store.py test_neon_migrations.py test_neon_data_safety.py test_auth.py
ruff check app api test_*.py scripts
black --check app api test_*.py scripts

# Local shelve mode
python app/phone_api.py

# Neon migration discovery and hosted integrity verification
python scripts/migrate_neon_schema.py
python scripts/check_neon_integrity.py
```

CI runs lint/format plus the smoke and seven-suite regression command on Python 3.11 and 3.14. A PostgreSQL 17 job separately exercises `test_neon_store.py` transaction behavior.

## Non-Obvious Facts

- Internal doubles/team math and history use `[offense, defense]`; the phone UI displays `Defense + Offense`.
- In `clerk` mode, legacy PIN/token headers are ignored. Clerk proves identity; Neon `app_users` owns authorization.
- Hosted match and lifecycle writes use Neon transactions, a transaction-scoped advisory lock, row locking, and persisted idempotency/audit records.
- Local shelve writes use `phone_api_write.lock`; match submissions without an `Idempotency-Key` also use the 60-second process-local duplicate fallback.
- Admin void/restore requires managed `admin` authorization, `Idempotency-Key`, optimistic `expected_version`, a reason, deterministic replay, and audit events.
- Hosted presence is durable in `player_presence` and expires after eight hours. Local shelve presence is process-local.
- `/api/health` is a readiness check and returns `503` when the configured store is unavailable or incompatible.

## Service Layer

- `app/services/match_service.py` — odds, rating updates, and lineup balancing
- `app/services/match_history.py` — local structured history and deterministic replay
- `app/services/phone_write_store.py` — shelve and Neon adapters, transactions, lifecycle, presence
- `app/services/auth.py` — Clerk verification and Neon role resolution
- `app/services/neon_migrations.py` and `app/services/neon_data_safety.py` — ordered migrations, integrity, export, and restore support

## Editing Rules

- Keep changes localized and behavior-preserving unless the task explicitly changes a contract.
- Check blueprint, template, static asset, service, and deployment boundaries before editing the composition root.
- Preserve auth roles, locking, idempotency, actor attribution, replay, and ordering semantics.
- Add comments only when intent is not obvious; check indentation carefully.

## Data Safety

- Before changing local shelve persistence, schema assumptions, or migration code, run `python scripts/backup_state.py`.
- Treat `app/playerdb*`, `app/recentplayers*`, `app/match_history*`, `app/match_events*`, and `app/rating_baselines*` as valuable legacy/local state; prefer additive compatibility.
- `backup_state.py` currently omits the lifecycle shelves, so preserve `match_events*` and `rating_baselines*` separately when they exist.
- Neon changes require ordered migrations under `scripts/sql/migrations/`, migration tests, store/integrity verification, and documented rollback/restore impact.
- Run hosted checks only against an explicitly selected non-production database unless production operation is the task. Encrypted restores must target an isolated Preview or restore-drill database.

## Verification Matrix

| Change | Minimum useful verification |
|---|---|
| Phone routes, templates, or static assets | `python -m unittest test_phone_api.py test_auth.py` |
| Match/ranking behavior | `python -m unittest test_match_flow.py` |
| Shared persistence/services | `python scripts/smoke_check.py` and `python -m unittest test_integration.py` |
| Neon store or transactions | `python -m unittest test_neon_store.py` with PostgreSQL integration when applicable |
| Neon migrations/data safety | `python -m unittest test_neon_migrations.py test_neon_data_safety.py` plus migration discovery/integrity checks |
| Full regression | CI-equivalent smoke, seven unittest modules, Ruff, and Black |

Update `README.md` and relevant `docs/` files when behavior, configuration, operations, API contracts, or recovery expectations change.
