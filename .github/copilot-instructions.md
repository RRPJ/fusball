# Copilot Instructions For This Repository

## Mission

- Preserve gameplay, ranking, and phone API behavior while modernizing safely.
- Prefer small changes with explicit verification.

## Read First

- `README.md` for run modes and entrypoints.
- `docs/development.md` for setup, lint, format, and smoke commands.
- `docs/architecture.md` for runtime boundaries.
- `docs/data-safety.md` before touching persistence or migrations.
- `docs/phone-api.md` and `docs/phone-write-policy.md` before changing request handling or write flows.

## Non-Obvious Repo Facts

- Primary runtime is `app/phone_api.py`; `api/index.py` exposes the same app for Vercel.
- Phone UI HTML/CSS/JS is embedded in `app/phone_api.py`.
- State is still shelve-backed under `app/`; treat `playerdb*`, `recentplayers*`, and `match_history*` as production-like data.
- Local production-style scripts target `app/`; development scripts may target `sandbox/dev-data`.
- Internal doubles/team rating math uses offense-first ordering; do not change presentation order assumptions without checking existing phone/history behavior.

## Default Workflow

1. State the intended behavior change.
2. Pick the smallest useful verification path.
3. Make the minimal localized edit.
4. Re-run the relevant checks.
5. Update docs if behavior, operations, or migration expectations changed.

## Verification Baseline

- General smoke: `python scripts/smoke_check.py`
- Phone/API regression: `python -m unittest test_phone_api.py`
- Match/ranking flow: `python -m unittest test_match_flow.py`
- Lint: `ruff check app api test_*.py scripts`
- Format check: `black --check app api test_*.py scripts`

## Editing Rules

- Keep logic changes localized; avoid unrelated formatting churn.
- Use clear names and small helpers for ranking, persistence, and transforms.
- Add comments only when intent is not obvious.
- Check indentation carefully before finalizing; indentation mistakes are a recurring regression source here.

## Data Safety Rules

- Back up state with `python scripts/backup_state.py` before changing persistence logic, migrations, or data-shape assumptions.
- Never mutate shelve schema casually.
- Prefer additive migrations over destructive rewrites.
- Document migration and rollback impact in `docs/data-safety.md` when behavior changes.

## Runtime Rules

- Preserve `/phone` and `/api/*` behavior unless the change explicitly targets those contracts.
- Preserve write-auth and conflict semantics unless the change intentionally updates that policy.
- Update docs and operational scripts when the supported phone workflow changes.
