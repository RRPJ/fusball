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

## Phone Support

The kiosk Pygame UI stays local and fixed-layout. Phone access is provided through a separate web/API path.

Run the phone API from `app/`:

```bash
cd app
python phone_api.py
```

To enable the minimal authenticated match-submit endpoint, set an operator token before starting the API.

Windows PowerShell:

```powershell
$env:FUSBALL_PHONE_API_TOKEN = "replace-with-a-shared-secret"
cd app
python phone_api.py
```

Then open:

- JSON API: `http://<host>:8080/api/leaderboard`
- Mobile page: `http://<host>:8080/phone`
- Match submit API: `POST http://<host>:8080/api/matches` with header `X-Operator-Token`

Phone page workflow:

1. Open `/phone`.
2. Choose `Singles` or `Doubles`.
3. Tap position buttons (`Red Offense`, `Red Defense`, `Blue Offense`, `Blue Defense`) and assign players from the player buttons list.
4. Tap score buttons for red/blue.
5. Enter operator token and tap `Submit Result`.
6. Confirm status text and refreshed leaderboard.

At-home test idea:

1. Run `phone_api.py` on your host machine.
2. Open the `/phone` URL from your phone browser on the same secure network path (for example Tailscale).
3. Confirm leaderboard rows match kiosk data.

Minimal match submit payload:

```json
{
	"team1": ["alice"],
	"team2": ["bob"],
	"score1": 5,
	"score2": 3
}
```

The first write slice is intentionally limited to finished singles or doubles results using existing players only. See `docs/phone-write-policy.md` for the current auth and conflict rules.

## Repository Guide

- Architecture: `docs/architecture.md`
- Development setup: `docs/development.md`
- Data safety and migration notes: `docs/data-safety.md`
- Phone write policy for the first remote submit slice: `docs/phone-write-policy.md`
- Prioritized improvement backlog: `docs/backlog.md`
- Modernization roadmap: `docs/modernization-plan.md`
- Contribution workflow: `CONTRIBUTING.md`

## Future Direction

Planned future exploration is focused on extending the current kiosk-first app without disrupting core match entry.

- Structured match history to support richer analytics beyond the current leaderboard.
- Prediction and insight features such as expected-result context, head-to-head records, form, and progression over time.
- Seasons, so current-season competition can reset cleanly while all-time rankings remain available.
- Tournament support as a separate exploration track once season/history foundations are in place.
- Authenticated phone workflows for remote match submission after auth and write-conflict rules are defined.

See `docs/backlog.md` for near-term slices and `docs/modernization-plan.md` for longer-term sequencing and rationale.