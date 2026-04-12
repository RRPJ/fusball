# Copilot Instructions For This Repository

## Goals

- Preserve gameplay and ranking behavior while modernizing safely.
- Prefer incremental changes with explicit verification steps.

## Project Conventions

- Launch app from `app/` directory (`python fusball.py`).
- Keep `lcars.py` compatibility unless a migration task explicitly removes it.
- Data is stateful and lives in shelve files under `app/`.
- Treat `playerdb*`, `recentplayers*`, and `tagdb*` as production-like data.
- Keep kiosk/fullscreen assumptions intact unless a task explicitly changes them.

## Safe Change Workflow

1. Describe intended behavior change.
2. Add or update a small verification path (smoke script or targeted test).
3. Apply the minimal code change.
4. Re-run verification.
5. Note any data migration impact in docs.

## Code Preferences

- Keep logic changes localized; avoid unrelated formatting churn.
- Use clear names and small helper functions for ranking/data transforms.
- Add comments only where intent is non-obvious.
- Take extra care with indentation when writing or editing code; indentation errors are a common regression source and must be checked before finalizing changes.

## Data Handling Rules

- Never mutate shelve schema casually.
- For schema changes, provide migration and rollback notes.
- Prefer additive migrations over destructive rewrites.

## UI Rules

- Maintain screen navigation semantics.
- Preserve touchscreen usability and large hit targets.
- Keep visual style consistent with existing LCARS components unless asked otherwise.
