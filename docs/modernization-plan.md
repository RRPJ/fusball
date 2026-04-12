# Modernization Plan

This plan keeps gameplay behavior stable while enabling steady modernization.

## Scope Of This Document

- This file is the long-horizon strategy (what and why).
- The active execution queue lives in `docs/backlog.md` (what next, in order).
- Keep this plan stable; update `docs/backlog.md` as work lands.

## Current Status Snapshot (2026-04-11)

Already completed in-repo:
- Canonical entrypoint is `app/fusball.py` with `app/lcars.py` compatibility retained.
- Startup diagnostics exist (`app/startup.py`) and run from app startup.
- CI runs lint/format checks and smoke checks (`.github/workflows/ci.yml`).
- Tooling is in place (`ruff`, `black`, and pre-commit hooks).
- Targeted behavior/regression tests exist for rating transitions, match save flow, and auto-balance behavior.
- Screen-level A3 refactor slice is complete for `entermatch.py` and `enteroutcome.py` with docstrings.
- Track C read-only phone slice exists (`app/phone_api.py`) with `/api/leaderboard` and `/phone`.
- Track C write baseline is shipped with token-protected `POST /api/matches` and `POST /api/players`; field validation items remain open in `docs/backlog.md`.
- Phone page now uses a guided step flow and supports player onboarding from mobile.
- Production/dev operational split exists for phone API launch (`run_phone_api_prod.bat`, `run_phone_api_dev.bat`, and `scripts/refresh_dev_sandbox.py`).

Still open:
- End-to-end phone validation across network/security boundaries (for example firewall/Tailscale path).
- Data portability and migration path beyond shelve.
- Structured match history needed for richer analytics, seasonal views, and future tournament features.

## Change Cadence

For each significant change set:

1. Implement one focused slice.
2. Run automated smoke check:
   - See `docs/development.md` for the current command.
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

Recommended incremental feature sequence after read-only phone support:
1. Add structured match history storage beside the existing text audit log.
2. Use that history to deliver prediction context and analytics (head-to-head, form, trend views, richer leaderboard filters).
3. Extend the phone path from read-only leaderboard to authenticated match submission with live refresh.
4. Reassess whether a larger web workflow is warranted only after those slices prove value.

## Workstream D: Data Layer Evolution

Current state:
- Python shelve files in app directory.
- Match history is still primarily represented as an append-only text audit trail plus current rating state.

Recommended path:
1. Add export/import tools (JSON snapshot format).
2. Add SQLite schema and dual-write migration mode.
3. Retire shelve only after verified parity and rollback plan.

Additional guidance:
- Treat structured match history as a prerequisite for analytics beyond simple current leaderboard views.
- Preserve `logfile.log` during migration as an audit/debug artifact even after richer history storage exists.
- Ensure any new history model can represent season boundaries and future tournament metadata without destructive schema churn.

Decision gates:
1. Repeatable backup and restore workflow is documented and tested.
2. Parity checks cover ranking, recent players, tags, and logging behavior.
3. Rollback path is validated before any destructive cutover.

## Workstream E: Analytics And Predictions

Goals:
- Expose more context before and after matches without changing core gameplay flow.
- Build on the existing odds/rating model instead of replacing it.
- Prefer analytics that can be validated from persisted match history.

Candidate features:
- Predicted result context before kickoff (expected winner, closeness, upset framing).
- Head-to-head records for player and doubles rivalries.
- Recent form and progression-over-time views.
- Additional leaderboard modes such as streaks, most improved, and time-window filters.
- Separate offense and defense trend views where the data supports it.

Decision gates:
1. Analytics derive from structured persisted history rather than fragile log parsing.
2. Kiosk UX remains quick to operate; heavier views can live on phone/web surfaces.
3. New metrics are explainable enough that players can understand why rankings or badges changed.

## Workstream F: Seasons And Historical Rankings

Goals:
- Support fresh competitive cycles without losing long-term history.
- Allow current-season and all-time views to coexist.

Recommended direction:
1. Introduce a season model before adding season-specific UI.
2. Start with manual season creation/rollover.
3. Consider quarterly auto-rollover only after the manual workflow is stable.

Design notes:
- Season changes should not erase all-time rankings or historical standings.
- Rating, standings, and analytics should be explicit about whether they are all-time or season-scoped.
- Season metadata should be represented in any future SQLite/history model from the start.

Decision gates:
1. The meaning of a season reset is defined clearly for ratings, logs, and exports.
2. Historical season standings remain inspectable after rollover.
3. All-time views remain available throughout the season system.

## Workstream G: Tournament Exploration

Goals:
- Leave room for organized events without destabilizing normal ad hoc match entry.
- Determine whether tournament data should influence normal rankings, and under what rules.

Recommended direction:
1. Treat tournaments as an exploration track, not an immediate core workflow.
2. Start by defining supported tournament shapes (for example single elimination, round robin, group plus knockout).
3. Decide whether tournaments are standalone, season-scoped, or both before building UI.

Decision gates:
1. Tournament flow does not complicate the default kiosk match flow for casual play.
2. Ranking impact rules are explicit before tournament results affect leaderboards.
3. Persistence design can represent tournament structure without blocking future migration work.

## Execution Note

- Use `docs/backlog.md` as the source of truth for the next concrete slice.
- Keep this document focused on direction, risk, and sequencing rationale.
