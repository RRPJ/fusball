---
applyTo: "app/services/**/*.py,app/dbmigration.py,test_match_flow.py,test_integration.py"
description: "Use when editing match services, player/history persistence, or migrations. Focuses on shelve safety, ranking semantics, rollback awareness, and validation."
---

# Stateful Service Instructions

- Read `docs/architecture.md` for module boundaries and `docs/data-safety.md` before changing persistence code.
- Treat `app/playerdb*`, `app/recentplayers*`, and `app/match_history*` as production-like state.
- Back up with `python scripts/backup_state.py` before changing persistence logic, schema assumptions, or migration code.
- Preserve ranking semantics: offense and defense ratings are tracked separately, and match/rating updates must remain behavior-compatible unless the change explicitly targets ranking logic.
- Prefer additive changes to stored data and clear migration paths over in-place rewrites.
- Do not mix unrelated refactors into service-layer persistence work; small diffs make rollback and inspection possible.
- When touching match history or migrations, consider rollback impact and update `docs/data-safety.md` if the recovery story changed.
- Use the smallest verification that exercises the changed path, typically `python scripts/smoke_check.py`, `python -m unittest test_match_flow.py`, or `python -m unittest test_integration.py`.