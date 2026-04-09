# LCARS Kickers Interface

LCARS Kickers is a touchscreen-first foosball score and leaderboard application.
It tracks player skill separately for offense and defense using TrueSkill.

## Quick Start

1. Create and activate a virtual environment.
2. Install dependencies.
3. Run smoke check.
4. Start the app from the `app/` directory.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python scripts/smoke_check.py
cd app
python fusball.py
```

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python scripts/smoke_check.py
cd app
python fusball.py
```

Windows double-click launcher:

- Double-click `launch_fusball.bat` in Windows Explorer.
- On first run it creates `.venv`, installs dependencies, and starts the app.
- On later runs it launches directly.

Python 3.14 note:

- On Python 3.14, this repository uses `pygame-ce` (which provides the `pygame` module).
- On Python 3.13 and older, it uses `pygame`.
- Dependency selection is automatic via environment markers in `requirements.txt`.

## What The Smoke Check Covers

- Ranking sort behavior on seeded sample data.
- Rank label generation.
- Win probability range checks.
- Basic shelve read/write assumptions.

Run it with:

```bash
python scripts/smoke_check.py
```

## Coding Standards

Install dev tooling:

```bash
pip install -r requirements-dev.txt
```

Run checks manually:

```bash
ruff check app/startup.py app/fusball.py scripts
black --check app/startup.py app/fusball.py scripts
```

Enable local pre-commit checks:

```bash
pre-commit install
```

## Data Safety

Operational data is stored in shelve files under `app/`.
Treat `playerdb*`, `recentplayers*`, and `tagdb*` as production-like state.

Before changing persistence or migration logic:

```bash
python scripts/backup_state.py
```

See `docs/data-safety.md` for policy details.

## Development Notes

- Development mode is enabled by default (`DEV_MODE = True` in `app/config.py`).
- The app is fullscreen and optimized for touchscreen kiosks.
- For a complete setup and troubleshooting guide, see `docs/development.md`.

## Repository Guide

- Architecture: `docs/architecture.md`
- Development setup: `docs/development.md`
- Data safety and migration notes: `docs/data-safety.md`
- Prioritized improvement backlog: `docs/backlog.md`
- Modernization roadmap: `docs/modernization-plan.md`
- Contribution workflow: `CONTRIBUTING.md`