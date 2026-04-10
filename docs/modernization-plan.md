# Modernization Plan

This plan keeps gameplay behavior stable while enabling steady modernization.

## Scope Of This Document

- This file is the long-horizon strategy (what and why).
- The active execution queue lives in `docs/backlog.md` (what next, in order).
- Keep this plan stable; update `docs/backlog.md` as work lands.

## Current Status Snapshot (2026-04-10)

Already completed in-repo:
- Canonical entrypoint is `app/fusball.py` with `app/lcars.py` compatibility retained.
- Startup diagnostics exist (`app/startup.py`) and run from app startup.
- CI runs lint/format checks and smoke checks (`.github/workflows/ci.yml`).
- Tooling is in place (`ruff`, `black`, and pre-commit hooks).
- Targeted behavior/regression tests exist for rating transitions, match save flow, and auto-balance behavior.
- Screen-level A3 refactor slice is complete for `entermatch.py` and `enteroutcome.py` with docstrings.
- Track C read-only phone slice exists (`app/phone_api.py`) with `/api/leaderboard` and `/phone`.

Still open:
- Remote reachability implementation choice (Option 1/2/3).
- End-to-end phone validation across network/security boundaries (for example firewall/Tailscale path).
- Auth and write-conflict policy before any remote write endpoint.
- Data portability and migration path beyond shelve.

## Change Cadence

For each significant change set:

1. Implement one focused slice.
2. Run automated smoke check:
   - `python scripts/smoke_check.py`
3. Run local app startup check:
   - `cd app`
   - `python fusball.py`
4. Human validation gate:
   - Verify at least one match flow manually in the UI.
   - Confirm leaderboard page still renders and updates.
5. Merge only after both automation and manual validation pass.

## Workstream A: Cleanup And Refactor

Goals:
- Reduce dead code and redundant modules.
- Standardize naming and import hygiene.
- Improve maintainability without changing behavior.

Decision gates:
1. No gameplay behavior drift versus smoke + manual checks.
2. Reduced complexity in the highest-churn modules.
3. Better confidence through focused regression coverage.

Execution detail:
- Keep concrete task breakdown in `docs/backlog.md`.

## Workstream B: Performance And Reliability

Goals:
- Improve observability before optimization work.
- Optimize only where profiling shows user-visible wins.
- Protect correctness and data safety while improving runtime behavior.

Execution detail:
- Keep concrete performance tasks and measurements in `docs/backlog.md`.

## Workstream C: Remote Reachability Options

Constraint:
- The current Pygame UI uses kiosk-oriented fixed layouts and should remain kiosk-only.
- Phone support should be delivered through a separate web/API path, not by reusing Pygame screens directly.

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

Early rollout preference:
1. Use Tailscale as the default secure connectivity layer for early phone testing.
2. Start with read-only phone workflows before enabling write actions.

Decision gates:
1. Host runtime is stable (app starts reliably and backups are repeatable).
2. Phone can read leaderboard from Android and iOS over the chosen secure path.
3. Write path is enabled only after auth and conflict rules are validated.

## Workstream D: Data Layer Evolution

Current state:
- Python shelve files in app directory.

Recommended path:
1. Add export/import tools (JSON snapshot format).
2. Add SQLite schema and dual-write migration mode.
3. Retire shelve only after verified parity and rollback plan.

Decision gates:
1. Repeatable backup and restore workflow is documented and tested.
2. Parity checks cover ranking, recent players, tags, and logging behavior.
3. Rollback path is validated before any destructive cutover.

## Execution Note

- Use `docs/backlog.md` as the source of truth for the next concrete slice.
- Keep this document focused on direction, risk, and sequencing rationale.
