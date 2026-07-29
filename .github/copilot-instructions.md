# Copilot Instructions For This Repository

## Mission

- Preserve gameplay, ranking, phone API, and recovery behavior while modernizing safely.
- Prefer small changes with explicit verification.

## Read First

- `README.md` for production, preview, and local run modes.
- `docs/architecture.md` for composition-root, blueprint, asset, and store boundaries.
- `docs/development.md` for setup and the full verification matrix.
- `docs/authentication.md` for Clerk modes and Neon-owned roles.
- `docs/data-safety.md` before persistence, migration, export, or restore work.
- `docs/phone-api.md` and `docs/phone-write-policy.md` before request or write-flow changes.

## Runtime Model

- Production is the Vercel Flask deployment through `api/index.py`, with Neon authoritative and `FUSBALL_AUTH_MODE=clerk`.
- Clerk authenticates hosted users; active Neon `app_users` rows authorize `reader`, `operator`, and `admin` capabilities.
- Preview must use an isolated Vercel Preview, Neon branch/project, and Clerk configuration. Never connect it to production Neon.
- Local development defaults to the shelve adapter under `app/` or `FUSBALL_PHONE_API_DB_DIR`. `legacy` PIN/token and `hybrid` modes are compatibility paths.
- `app/phone_api.py` is the composition root/local launcher. Routes live in `app/blueprints/`; templates and browser assets live in `app/templates/` and `app/static/`.
- Hosted presence uses Neon `player_presence` rows with an eight-hour expiry; local shelve presence is process-local.
- Internal doubles/rating order is `[offense, defense]`; phone presentation is Defense + Offense.

## Default Workflow

1. State the intended behavior change and affected runtime mode.
2. Read the relevant contract and safety docs.
3. Make the smallest localized edit across the correct blueprint/template/static/service boundary.
4. Run targeted checks, escalating to the full matrix for cross-cutting changes.
5. Update docs when behavior, operations, configuration, migration, or recovery expectations change.

## Verification Baseline

- Smoke: `python scripts/smoke_check.py`
- Full regression: `python -m unittest test_phone_api.py test_match_flow.py test_integration.py test_neon_store.py test_neon_migrations.py test_neon_data_safety.py test_auth.py`
- Lint: `ruff check app api test_*.py scripts`
- Format: `black --check app api test_*.py scripts`
- Auth smoke: `python scripts/smoke_phone_api_auth.py`
- Neon migration discovery: `python scripts/migrate_neon_schema.py`
- Neon integrity, with an explicitly selected database: `python scripts/check_neon_integrity.py`

CI runs the smoke and seven unittest modules on Python 3.11 and 3.14, plus `test_neon_store.py` against PostgreSQL 17.

## Editing Rules

- Keep logic changes localized and avoid unrelated formatting churn.
- Preserve route contracts, Clerk role enforcement, managed actor attribution, transaction boundaries, idempotency, audit events, and replay parity.
- Preserve local `phone_api_write.lock` conflict behavior and the 60-second no-key duplicate fallback.
- Do not apply the local file-lock model to Neon: hosted writes use transactions, a transaction-scoped advisory lock, row locking, and persisted idempotency.
- Admin void/restore remains managed-admin-only and requires a reason, `expected_version`, and `Idempotency-Key`.
- Add comments only when intent is not obvious; check indentation carefully.

## Data Safety Rules

- Before changing local shelve persistence or data-shape assumptions, run `python scripts/backup_state.py`.
- Treat `app/playerdb*`, `app/recentplayers*`, `app/match_history*`, `app/match_events*`, and `app/rating_baselines*` as valuable compatibility state; never assume they are disposable.
- `backup_state.py` does not currently copy the lifecycle shelves; preserve `match_events*` and `rating_baselines*` separately when present.
- Use additive ordered SQL migrations under `scripts/sql/migrations/`; never rewrite an applied migration.
- Neon-sensitive changes require migration/store/data-safety tests, integrity verification, and a documented encrypted-export and isolated-restore story.
- Never run Preview, parity, migration, or restore verification against production Neon unless production operation is explicitly the task.

## Runtime Rules

- Preserve `/`, `/login`, `/phone`, and `/api/*` behavior unless the task explicitly changes those contracts.
- In `clerk` mode, legacy headers are ignored; do not weaken strict production auth.
- Preserve `/api/health` readiness semantics, including `503` for unavailable or incompatible stores.
- Preserve durable hosted presence and process-local shelve presence semantics.
- Update relevant docs and operational commands whenever supported workflows change.
