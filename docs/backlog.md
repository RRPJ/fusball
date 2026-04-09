# Improvement Backlog

Use this file to prioritize changes in small, safe slices.

## Track A: Stabilize Existing Behavior

- [ ] Add startup diagnostic logging for missing assets and db files.
- [ ] Add a reproducible smoke test for ranking + persistence operations.
- [ ] Add CI checks for install + smoke test.
- [ ] Validate behavior with an archived production db snapshot.

## Track B: Developer Experience

- [ ] Pin dependency versions.
- [ ] Add lint/format tooling and pre-commit hooks.
- [ ] Add docs for screen flow and data model.

## Track C: UX Improvements

- [ ] Add clearer validation messages for invalid team composition.
- [ ] Improve keyboard/search feedback in match entry.
- [ ] Add compact leaderboard filters (time window / min games).

## Track D: Data Layer Modernization

- [ ] Design portable storage model (SQLite recommended).
- [ ] Build one-way migration from shelve to SQLite.
- [ ] Keep compatibility reader for old backups.

## Track E: Optional Features

- [ ] Multi-device score entry.
- [ ] Network sync and conflict handling.
- [ ] Match history analytics dashboard.
