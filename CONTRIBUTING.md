# Contributing

## Development Flow

1. Create a branch.
2. Run setup from [docs/development.md](docs/development.md).
3. Run `python scripts/smoke_check.py` before opening a PR.
4. Keep changes small and behavior-preserving unless intentionally changing gameplay.

## Communication Expectation

- For every code or documentation change, explain what changed and why.
- Include a short validation note (what was run/checked) and any known trade-offs.
- Write explanations for maintainers who are learning the codebase as changes land.

## Coding Standards

- Install dev tools with `pip install -r requirements-dev.txt`.
- Run lint: `ruff check app/startup.py app/fusball.py scripts`.
- Run formatting check: `black --check app/startup.py app/fusball.py scripts`.
- Enable local hooks: `pre-commit install`.
- For changed functions, add concise docstrings when intent is not immediately obvious.

## Naming Policy

- `fusball.py` is the canonical entrypoint for new docs/scripts.
- `lcars.py` remains for backward compatibility during migration.
- Avoid broad symbol renames from `Lcars*` unless part of an explicit migration slice.

## Data Safety Requirements

- Before modifying persistence logic, create a backup:
  - `python scripts/backup_state.py`
- Document migration impact in [docs/data-safety.md](docs/data-safety.md).

## Pull Request Checklist

- [ ] Smoke check passes locally.
- [ ] Ruff and Black checks pass locally.
- [ ] Any data-shape changes have migration and rollback notes.
- [ ] README/docs are updated for behavior or workflow changes.
- [ ] UI changes preserve touchscreen-first navigation and hit targets.
