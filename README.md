# Fusball Phone API

Fusball is a phone-first foosball match and leaderboard service. It tracks
offense and defense skill separately with TrueSkill and serves the phone UI and
JSON API from one Flask application.

<img width="774" height="1283" alt="Fusball phone interface" src="https://github.com/user-attachments/assets/f06b7698-7729-4ac1-9478-a4dc9ed0efbd" />

## Supported Environment Model

| Environment | Runtime | Persistence | Authentication |
| --- | --- | --- | --- |
| Production | Vercel through `api/index.py` and `vercel.json` | Dedicated Neon production database | Strict Clerk (`FUSBALL_AUTH_MODE=clerk`) with roles from Neon `app_users` |
| Preview | Vercel Preview | Isolated Neon preview branch/project | Clerk configured for the exact preview origin |
| Local development | `app/phone_api.py` | Shelve in `app/` or `FUSBALL_PHONE_API_DB_DIR` | Legacy PIN/token compatibility by default |
| Cloud-like local testing | `app/phone_api.py` | Explicit Neon test/preview database | Clerk, normally strict mode |

Do not connect Vercel Preview or local experiments to the production Neon
database. Shelve and shared PIN/token modes remain supported for local
development and rollback compatibility; they are not the hosted production
standard.

## What It Does

- Serves the phone UI at `/phone` and managed sign-in at `/login`
- Exposes health, leaderboard, player, presence, odds, stats, history, match,
  and correction endpoints under `/api/*`
- Uses Neon transactions for hosted mutations; rating and lifecycle writes add
  advisory locking, idempotency, audit events, and deterministic replay
- Keeps internal doubles arrays offense-first (`[offense, defense]`) while the
  phone UI displays `Defense + Offense`

## Local Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python scripts\smoke_check.py
python app\phone_api.py
```

Open:

- Phone UI: `http://127.0.0.1:8080/phone`
- Health/readiness: `http://127.0.0.1:8080/api/health`

Without a writer PIN hash or operator token, this direct launch allows open
legacy reads but returns `503` for writes.

For an isolated shelve sandbox with prompted compatibility credentials, use
`run_phone_api_dev.bat`. The `start_phone_api_service.bat`,
`stop_phone_api_service.bat`, and `status_phone_api_service.bat` files are
historical local wrappers, not hosted production operation. Their watchdog
still probes the legacy `/health` path rather than `/api/health`; use the
direct or development launcher until that wrapper is updated.

See `docs/development.md` for local PIN setup, cloud-like Clerk/Neon testing,
Vercel environment mapping, migrations, and verification commands.

## Hosted Production Requirements

The branch implements the Vercel + Neon + Clerk runtime, but provider
configuration and a real deployment are external operations. Before calling a
production rollout complete:

1. Configure a dedicated production `DATABASE_URL`.
2. Set `FUSBALL_AUTH_MODE=clerk` explicitly and configure the Clerk keys and
   exact authorized frontend origin.
3. Apply ordered migrations and run the Neon integrity check.
4. Provision active `reader`, `operator`, and `admin` users as required in
   `app_users`.
5. Record a successful isolated restore drill and preview validation.
6. Record the Vercel deployment URL/ID, commit, health result, Clerk role
   checks, and a controlled post-deploy read/write check.

Repository tests demonstrate implementation behavior; they do not prove that
Vercel, Neon, Clerk, DNS, secrets, user provisioning, backups, or restore
drills have been configured in an external environment.

## Data Safety

Neon is authoritative in hosted environments. Use encrypted logical exports,
provider recovery, integrity checks, and isolated restore drills. Never store
database URLs, Clerk secrets, backup keys, or backup artifacts in the
repository.

Local shelve state (`playerdb*`, `recentplayers*`, `match_history*`,
`match_events*`, `rating_baselines*`, and `logfile.log`) is compatibility
data. Back it up before local persistence or migration work:

```powershell
python scripts\backup_state.py
```

See `docs/data-safety.md` for hosted and local procedures.

## Repository Guide

- Architecture: `docs/architecture.md`
- Development and deployment verification: `docs/development.md`
- Authentication and role provisioning: `docs/authentication.md`
- Data safety and migration: `docs/data-safety.md`
- Phone API endpoint reference: `docs/phone-api.md`
- Write, conflict, and audit policy: `docs/phone-write-policy.md`
- Prioritized backlog: `docs/backlog.md`
- Implementation status: `docs/reliability-maintainability-plan.md`
- Contribution workflow: `CONTRIBUTING.md`
