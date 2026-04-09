# Modernization Plan

This plan keeps gameplay behavior stable while enabling steady modernization.

## Change Cadence

For each significant change set:

1. Implement one focused slice.
2. Run automated smoke check:
   - `python scripts/smoke_check.py`
3. Run local app startup check:
   - `cd app`
   - `python lcars.py`
4. Human validation gate:
   - Verify at least one match flow manually in the UI.
   - Confirm leaderboard page still renders and updates.
5. Merge only after both automation and manual validation pass.

## Workstream A: Cleanup And Refactor

Goals:
- Reduce dead code and redundant modules.
- Standardize naming and import hygiene.
- Improve maintainability without changing behavior.

Phase A1 (safe, immediate):
- Remove unused imports and obvious no-op code.
- Document legacy files that are candidates for archive/removal.
- Keep all behavior and data formats unchanged.

Phase A2 (medium risk):
- Split very long screen modules into smaller helpers.
- Move ranking and persistence helpers into explicit service modules.
- Add targeted tests around ranking transitions.

Phase A3 (higher impact):
- Introduce static tooling (ruff + formatting + pre-commit).
- Add typed interfaces for core data paths.

## Workstream B: Performance And Reliability

Near-term:
- Add startup diagnostics for missing assets and db files.
- Cache repeated expensive operations where safe.
- Add explicit error logs for file/db failures.

Mid-term:
- Profile key UI update paths on realistic data sizes.
- Reduce redundant shelve opens/reads in hot paths.

## Workstream C: Remote Reachability Options

Option 1: Remote Desktop To Host Machine
- Examples: Tailscale + RDP, AnyDesk, RustDesk.
- Pros: fastest, no app changes, full UI preserved.
- Cons: tied to host session/peripherals; not true multi-user app.

Option 2: Kiosk Host + Thin Operator API
- Keep Pygame kiosk local.
- Add a small HTTP API (FastAPI/Flask) for remote tasks (add player, submit result, read leaderboard).
- Pros: incremental, keeps kiosk UX, unlocks automation.
- Cons: need auth, validation, and conflict handling with local writes.

Option 3: Full Web Frontend Replacement
- Replace Pygame UI with web app and backend service.
- Pros: best long-term remote access and multi-device UX.
- Cons: largest rewrite, highest risk, requires staged migration.

Recommended sequence:
1. Start with Option 1 for immediate remote usability.
2. Build Option 2 API for real operational remote workflows.
3. Decide later whether Option 3 is worth full migration cost.

## Workstream D: Data Layer Evolution

Current state:
- Python shelve files in app directory.

Recommended path:
1. Add export/import tools (JSON snapshot format).
2. Add SQLite schema and dual-write migration mode.
3. Retire shelve only after verified parity and rollback plan.

## First Backlog Slice (proposed)

1. Safe code cleanup pass (imports + dead references).
2. Add startup diagnostics for db/asset prerequisites.
3. Validate with smoke check + manual launch.
4. Add issue list for files pending archive/removal.
