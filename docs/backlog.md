# Improvement Backlog

Use this file to prioritize changes in small, safe slices.

Scope note:
- This file is the execution queue (ordered next actions).
- `docs/modernization-plan.md` is the longer-term strategy and rationale.

## Completed Foundation (Done)

- [x] Add startup diagnostic logging for missing assets and db files.
- [x] Add reproducible smoke checks for ranking/probability behavior.
- [x] Add CI checks for lint + smoke test.
- [x] Add lint/format tooling and pre-commit hooks.
- [x] Create `fusball.py` as canonical entrypoint while keeping `lcars.py` compatibility.
- [x] Extract service layer for player store, match logic, and match logging.
- [x] Archive kiosk/touchscreen deployment files under `legacy/`.

## Next Priority: Track A2 (Targeted Test Coverage)

- [x] Add test for rating update transitions (win/loss and draw cycles).
- [x] Add test for match save flow (persistence + logfile entry format).
- [x] Add regression test for auto-balance lineup selection behavior.

## Next Priority: Track A3 (Screen Refactor)

- [x] Split long methods in `app/screens/entermatch.py` into smaller helpers.
- [x] Split long methods in `app/screens/enteroutcome.py` into smaller helpers.
- [x] Add concise docstrings for complex screen/service methods.

## Track C: Smartphone Access Path

- [ ] Option 2 spike: add thin operator HTTP API (FastAPI/Flask) for leaderboard read and match submit.
- [ ] Define auth and write-conflict rules between local UI and remote API calls.
- [ ] Validate one end-to-end smartphone workflow (read leaderboard, submit result).

## Track D: Data Layer Modernization

- [ ] Define portable storage model (SQLite recommended).
- [ ] Add export/import snapshot path from shelve.
- [ ] Add migration prototype (shelve -> SQLite) with rollback notes.
- [ ] Keep compatibility reader for old backups until parity is verified.

## Optional UX Enhancements

- [ ] Improve validation messages for invalid team composition.
- [ ] Improve keyboard/search feedback in match entry.
- [ ] Add compact leaderboard filters (time window / min games).
- [ ] Add match history analytics dashboard.
