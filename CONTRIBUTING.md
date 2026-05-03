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

- Use `docs/development.md` as the source of truth for dev-tool installation, lint/format commands, and pre-commit setup.
- For changed functions, add concise docstrings when intent is not immediately obvious.

## Naming Policy

- Repository-facing names should describe the phone API workflow and use Fusball terminology.
- Remove or rewrite legacy kiosk, LCARS, and kickers references when they no longer serve an active compatibility need.

## Data Safety Requirements

- Before modifying persistence logic, run `python scripts/backup_state.py`.
- Document migration impact in [docs/data-safety.md](docs/data-safety.md).

## Automated Checks

CI runs lint/format checks and smoke checks on push/PR.

- Workflow: `.github/workflows/ci.yml`
- Runbook and local commands: `docs/development.md`

## Pull Request Checklist

- [ ] Smoke check passes locally.
- [ ] Ruff and Black checks pass locally.
- [ ] Any data-shape changes have migration and rollback notes.
- [ ] README/docs are updated for behavior or workflow changes.
