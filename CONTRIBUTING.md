# Contributing

## Development Flow

1. Create a branch.
2. Run setup from [docs/development.md](docs/development.md).
3. Run `python scripts/smoke_check.py` before opening a PR.
4. Keep changes small and behavior-preserving unless intentionally changing gameplay.

## Data Safety Requirements

- Before modifying persistence logic, create a backup:
  - `python scripts/backup_state.py`
- Document migration impact in [docs/data-safety.md](docs/data-safety.md).

## Pull Request Checklist

- [ ] Smoke check passes locally.
- [ ] Any data-shape changes have migration and rollback notes.
- [ ] README/docs are updated for behavior or workflow changes.
- [ ] UI changes preserve touchscreen-first navigation and hit targets.
