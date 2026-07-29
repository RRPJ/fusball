# Fusball Phone API

Fusball is a phone-first match and leaderboard service for foosball play. It tracks player skill separately for offense and defense using TrueSkill and exposes both a browser UI and JSON endpoints from the same runtime.

<img width="774" height="1283" alt="image" src="https://github.com/user-attachments/assets/f06b7698-7729-4ac1-9478-a4dc9ed0efbd" />

## What It Does

- Serves a phone-friendly operator page at `/phone`
- Exposes leaderboard, player, presence, odds, stats, and match endpoints under `/api/*`
- Persists ratings and match history in the existing shelve-backed data model under `app/`
- Supports split read/write PIN auth with legacy token fallback where needed

## Quick Start

1. Install Python and project dependencies using `docs/development.md`.
2. Run `python scripts/smoke_check.py`.
3. Start the phone API using one of the supported paths.

Production service flow on Windows:

1. Double-click `start_phone_api_service.bat`.
2. Enter the writer PIN when prompted.
3. Open `http://<host>:8080/phone` from a phone or browser.
4. Stop the service with `stop_phone_api_service.bat`.

Useful companion commands:

- `status_phone_api_service.bat` shows watchdog, API, and log status.
- `run_phone_api_dev.bat` starts the sandbox-backed development runtime.

Direct local run is also supported:

```bash
cd app
python phone_api.py
```

## Data Safety

Operational data is stored in shelve files under `app/`.
Treat `playerdb*`, `recentplayers*`, and `match_history*` as production-like state.

Before changing persistence or migration logic:

```bash
python scripts/backup_state.py
```

Historical kiosk-only artifacts have been retired from the active workflow. Keep `backups/` as the archive for old state snapshots.

Hosted Neon deployments use encrypted logical exports and isolated restore
drills. See `docs/data-safety.md`; never store backup artifacts or encryption
keys in the repository.

## Primary URLs

- Phone UI: `http://<host>:8080/phone`
- Health: `http://<host>:8080/api/health`
- Leaderboard API: `http://<host>:8080/api/leaderboard`

## Repository Guide

- Architecture: `docs/architecture.md`
- Development setup: `docs/development.md`
- Data safety and migration notes: `docs/data-safety.md`
- Phone API endpoint reference: `docs/phone-api.md`
- Phone write auth/conflict policy: `docs/phone-write-policy.md`
- Authentication and authorization: `docs/authentication.md`
- Prioritized improvement backlog: `docs/backlog.md`
- Reliability and maintainability roadmap: `docs/reliability-maintainability-plan.md`
- Contribution workflow: `CONTRIBUTING.md`

## Direction

The repository now targets a single runtime: the Fusball phone API. Future work is focused on safer data evolution, richer match history, stronger operations, and better phone-native workflows rather than maintaining a local kiosk UI.
