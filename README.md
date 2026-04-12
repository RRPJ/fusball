# LCARS Kickers Interface

LCARS Kickers is a touchscreen-first foosball score and leaderboard application.
It tracks player skill separately for offense and defense using TrueSkill.

## Quick Start

Setup and run instructions are maintained in `docs/development.md`.

Canonical flow:
1. Create/activate a venv.
2. Install dependencies.
3. Run `python scripts/smoke_check.py`.
4. Launch from `app/` with `python fusball.py`.

See `docs/development.md` for platform-specific commands.

Windows double-click launcher:

- Double-click `launch_fusball.bat` in Windows Explorer.
- On first run it creates `.venv`, installs dependencies, and starts the app.
- On later runs it launches directly.

Advanced launcher option:

- Set `FUSBALL_NO_LAUNCH=1` to perform setup checks without starting the app.

Python version guidance:

- Python 3.14 is supported on Windows using `pygame-ce`.
- Python 3.11+ is supported for baseline development.
- Dependency selection is automatic via environment markers in `requirements.txt`.

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
- Coding standards, lint/format, pre-commit setup, and troubleshooting live in `docs/development.md`.

## Phone Support

The kiosk Pygame UI stays local and fixed-layout. Phone access is provided through a separate web/API path.

Preferred production phone API service flow (manual, double-click):

- Start (with token prompt + watchdog): `start_phone_api_service.bat`
- Stop (also closes the Tailscale app): `stop_phone_api_service.bat`
- Status: `status_phone_api_service.bat`

Compatibility launchers:

- `run_phone_api_prod.bat` delegates to the preferred production service start script.
- `run_phone_api_dev.bat` starts the development sandbox API flow.

Direct run is also supported (advanced/manual):

```bash
cd app
python phone_api.py
```

Operator token setup options:

1. Enter token when prompted by `start_phone_api_service.bat`.
2. Set environment variable `FUSBALL_PHONE_API_TOKEN`.
3. Pass token directly to `scripts/phone_stack_control.ps1`.

Env-var example (Windows PowerShell):

```powershell
$env:FUSBALL_PHONE_API_TOKEN = "replace-with-a-shared-secret"
cd app
python phone_api.py
```

Primary URLs:

- Mobile page: `http://<host>:8080/phone`
- Leaderboard API: `http://<host>:8080/api/leaderboard`

Prod vs dev data safety:

- Production service start script ensures the Windows Tailscale service is running and opens the Tailscale app when installed, then reads/writes `app/` data and creates a backup on startup.
- Production service watchdog monitors `/health` and restarts the API after repeated failures.
- Production service stop closes the Tailscale app when it was opened for phone access, but leaves the Windows Tailscale service installed/runnable.
- Development launcher runs against `sandbox/dev-data` so test matches do not affect real rankings.
- Refresh the dev sandbox manually when needed with `python scripts/refresh_dev_sandbox.py`.

For endpoint-level request/response details, see `docs/phone-api.md`.
For auth/conflict behavior, see `docs/phone-write-policy.md`.

## Repository Guide

- Architecture: `docs/architecture.md`
- Development setup: `docs/development.md`
- Data safety and migration notes: `docs/data-safety.md`
- Phone API endpoint reference: `docs/phone-api.md`
- Phone write auth/conflict policy: `docs/phone-write-policy.md`
- Prioritized improvement backlog: `docs/backlog.md`
- Modernization roadmap: `docs/modernization-plan.md`
- Contribution workflow: `CONTRIBUTING.md`

## Documentation Source Of Truth

- Strategy, rationale, and sequencing principles: `docs/modernization-plan.md`
- Ordered execution status and next slices: `docs/backlog.md`
- Setup, smoke check, lint/format, and pre-commit commands: `docs/development.md`

## Future Direction

Planned future exploration is focused on extending the current kiosk-first app without disrupting core match entry.

- Structured match history to support richer analytics beyond the current leaderboard.
- Prediction and insight features such as expected-result context, head-to-head records, form, and progression over time.
- Seasons, so current-season competition can reset cleanly while all-time rankings remain available.
- Tournament support as a separate exploration track once season/history foundations are in place.
- Broader authenticated phone workflows beyond the current baseline (for example match correction/admin operations) after structured history and stronger data guarantees are in place.

See `docs/backlog.md` for near-term slices and `docs/modernization-plan.md` for longer-term sequencing and rationale.