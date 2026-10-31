# Development Setup

Production is the Vercel-hosted Flask app with Neon-authoritative persistence
and strict Clerk authentication. This guide also keeps the shelve and shared
credential paths available for local development and rollback compatibility.
For production-like development and manual testing, use Vercel Preview with
isolated Neon and Clerk configurations. The future of shelve compatibility is
discussed in `architecture.md`; it remains supported until explicitly retired.

## Supported Baseline

- Python 3.11 and 3.14 are exercised by CI.
- Windows 11 and Ubuntu 22.04+ are supported development environments.
- `api/index.py` is the Vercel entrypoint; `app/phone_api.py` is the direct
  local entrypoint.

## Install

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

## Local Shelve Workflow

The smallest local workflow uses shelve state and `legacy` auth:

```powershell
$env:FUSBALL_AUTH_MODE = "legacy"
python scripts\smoke_check.py
python app\phone_api.py
```

With no `WRITE_PIN_HASH` or `FUSBALL_PHONE_API_TOKEN`, this direct launch
allows open legacy reads but returns `503` for writes.

By default, direct local execution reads `app/playerdb*`,
`app/recentplayers*`, and `app/match_history*`. Set
`FUSBALL_PHONE_API_DB_DIR` to use another directory.

For an isolated sandbox and prompted credentials:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File scripts\run_phone_api_dev.ps1 -PromptPins
```

Explicit local PINs:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File scripts\run_phone_api_dev.ps1 `
  -ReadPin "read1234" -WritePin "write5678"
```

`run_phone_api_dev.bat` calls the same PowerShell script and writes to
`sandbox/dev-data`. If no split PIN hashes are present, the launcher can fall
back to `FUSBALL_PHONE_API_TOKEN`.

## Cloud-Like Local Workflow

Use a disposable Neon database and a Clerk test/development instance. Never
point local cloud-like testing at production Neon.

```powershell
$env:DATABASE_URL = "<isolated-neon-url>"
$env:FUSBALL_AUTH_MODE = "clerk"
$env:CLERK_SECRET_KEY = "<clerk-secret>"
$env:CLERK_PUBLISHABLE_KEY = "<clerk-publishable-key>"
$env:CLERK_AUTHORIZED_PARTIES = "http://127.0.0.1:8080"
# Optional only when origin derivation from the publishable key is unsuitable:
$env:CLERK_FRONTEND_API_URL = "https://<clerk-frontend-origin>"

python scripts\migrate_neon_schema.py --apply
python scripts\check_neon_integrity.py
python app\phone_api.py
```

Open `http://127.0.0.1:8080/phone`. Provision the Clerk subject in that
database's `app_users` table as described in `authentication.md`.

`DATABASE_URL` selects the Neon adapter. Without it, the runtime selects
shelve. Strict Clerk also requires a valid publishable key, secret key,
authorized party, and Neon database.

## Vercel Preview And Production

`vercel.json` sends all routes to `api/index.py`. Configure variables in the
matching Vercel environment rather than committing an env file.

| Variable | Preview | Production |
| --- | --- | --- |
| `DATABASE_URL` | Isolated Neon preview branch/project | Dedicated Neon production database |
| `FUSBALL_AUTH_MODE` | `clerk` | `clerk` |
| `CLERK_SECRET_KEY` | Preview/test Clerk key | Production Clerk key |
| `CLERK_PUBLISHABLE_KEY` | Matching preview/test key | Matching production key |
| `CLERK_AUTHORIZED_PARTIES` | Exact preview origin(s) | Exact production origin(s) |
| `CLERK_FRONTEND_API_URL` | Optional derivation fallback | Optional derivation fallback |

Operational-only secrets:

- `FUSBALL_BACKUP_KEY`: encryption key for hosted exports/restores
- `RESTORE_DATABASE_URL`: empty isolated restore target

These belong in the approved environment used to run recovery commands; they
do not need to be exposed to the Vercel application runtime.

Local/rollback compatibility variables:

- `FUSBALL_PHONE_API_DB_DIR`
- `READ_PIN_HASH`
- `WRITE_PIN_HASH`
- `FUSBALL_PHONE_API_TOKEN`

Do not use local shelve as a hosted failover store. Do not give Preview the
Production `DATABASE_URL`, Clerk secret, or backup target.

## Database Setup And Verification

List migrations without applying them:

```powershell
python scripts\migrate_neon_schema.py
```

Apply ordered migrations:

```powershell
python scripts\migrate_neon_schema.py --database-url "<database-url>" --apply
```

Applied versions and checksums are recorded in `schema_migrations`. Never edit
an applied migration; add the next numbered file under
`scripts/sql/migrations/`.

Dry-run a shelve import, then apply only to the intended empty or controlled
target:

```powershell
python scripts\migrate_shelve_to_neon.py --db-dir app
python scripts\migrate_shelve_to_neon.py --db-dir app `
  --database-url "<database-url>" --apply
```

The current importer reads `playerdb*`, `recentplayers*`, and
`match_history*`. It derives baselines and synthetic submit events, but it
does not import local `match_events*` or `rating_baselines*`, and imported
lifecycle columns are reset to active version 1. Do not use it to cut over a
local history containing void/restore state or lifecycle/idempotency
provenance that must be preserved; see `data-safety.md`.

Run exact parity when migrating known shelve state:

```powershell
python scripts\smoke_neon_parity.py --db-dir app `
  --database-url "<database-url>" --mode strict
```

`--mode counts` is a faster diagnostic, not a cutover substitute. Strict mode
compares exact ratings, recent ordering, match payloads, lifecycle state, and
replay/audit integrity.

Run hosted integrity independently:

```powershell
python scripts\check_neon_integrity.py --database-url "<database-url>"
```

`GET /api/health` is a readiness check. Neon mode returns `503` if the
connection or exact ordered schema is unavailable/incompatible.

## Authentication Verification

The compatibility smoke script exercises PIN/token behavior; it does not
obtain a Clerk browser session:

```powershell
python scripts\smoke_phone_api_auth.py `
  --base-url http://127.0.0.1:8080 `
  --expect-auth --read-pin "<read-pin>" --write-pin "<write-pin>"
```

For strict Clerk, validate through `/login` and `/phone`, then use
`GET /api/auth/me` to confirm the active subject and role. Verify:

- anonymous public leaderboard, stats, and profiles work; other strict-mode
  reads and writes are rejected;
- `reader` cannot write;
- `operator` can perform normal writes but not admin corrections;
- `admin` can list and correct matches;
- disabled or unprovisioned Clerk subjects are rejected;
- PIN/token headers do not bypass strict mode.

Perform mutating checks only against isolated preview/test data.

On an isolated dev or preview deployment, check `/` anonymously and while
signed in; exercise every metric and period, including bounded-only Improved,
and verify profiles, lineups, scores, rating changes, and no H2H action. Check
that the phone link signs in to `/phone`. In browser developer tools simulate
offline and service failures with and without a saved selection: verify the
stale metric/period, disabled alternatives, unavailable profiles, error message,
and unavailable state without a snapshot. Inspect public JSON for absence of
rating means and uncertainties, and verify protected reads and writes retain
their policies. Check legacy and hybrid with read PINs where available.
Preview observations are not evidence of production deployment.

## Backup And Restore Drill

Set `FUSBALL_BACKUP_KEY` in an approved administrative environment:

```powershell
python scripts\export_neon_backup.py `
  --database-url "<source-url>" `
  --output "C:\secure-backups\fusball-<timestamp>.fusball-backup"

$env:RESTORE_DATABASE_URL = "<empty-isolated-url>"
python scripts\restore_neon_backup.py `
  "C:\secure-backups\fusball-<timestamp>.fusball-backup" `
  --target-environment restore-drill --confirm-isolated-target
```

The restore command defaults to `RESTORE_DATABASE_URL` and refuses a
production target label. Follow it with the integrity check and an app read
against the restored database. Store the encrypted artifact outside the
repository.

## Regression And Style Checks

Run the smallest relevant checks for the change, escalating to the full
regression matrix for cross-cutting changes:

| Change | Minimum useful verification |
| --- | --- |
| Phone routes, templates, or static assets | `python -m unittest test_phone_api.py test_auth.py` |
| Match/ranking behavior | `python -m unittest test_match_flow.py` |
| Shared persistence/services | `python scripts/smoke_check.py` and `python -m unittest test_integration.py` |
| Neon store or transactions | `python -m unittest test_neon_store.py` with PostgreSQL integration when applicable |
| Neon migrations/data safety | `python -m unittest test_neon_migrations.py test_neon_data_safety.py` plus migration discovery and integrity checks against an explicitly selected non-production database |
| Full regression | CI smoke and regression tests, Ruff, and Black below |

The CI regression matrix runs:

```powershell
python scripts\smoke_check.py
python -m unittest test_phone_api.py test_match_flow.py test_integration.py `
  test_neon_store.py test_neon_migrations.py test_neon_data_safety.py test_auth.py
```

The PostgreSQL transaction tests require `TEST_DATABASE_URL`; without it,
their database-backed cases are skipped.

Lint and format:

```powershell
ruff check app api test_*.py scripts
black --check app api test_*.py scripts
```

Optional hooks:

```powershell
pre-commit install
```

## Rollout Evidence

Passing repository tests proves branch behavior, not provider deployment.
Keep a redacted rollout record containing:

- Vercel Preview/Production deployment URL or ID and commit SHA;
- intended Vercel-to-Neon environment mapping;
- migration and integrity output with timestamps;
- `/api/health` readiness result;
- Clerk authorized-party and role checks;
- strict-mode negative auth checks;
- isolated restore-drill result and credential cleanup;
- controlled preview and production read/write observations.

Do not claim Preview or Production rollout complete until those external checks
have actually been performed. Never record secrets or full connection strings.

## Troubleshooting

Hosted:

- Startup failure in `clerk` mode: verify all Clerk values, exact authorized
  origins, and `DATABASE_URL`.
- `/api/health` returns `503`: check Neon reachability and run
  `migrate_neon_schema.py` plus `check_neon_integrity.py`.
- Signed in but unauthorized: provision an active `app_users` row using the
  immutable Clerk subject.
- Preview changes production data: stop writes immediately and replace the
  preview `DATABASE_URL` with an isolated target.

Local:

- Writes return `503`: configure `WRITE_PIN_HASH` or
  `FUSBALL_PHONE_API_TOKEN` in `legacy` mode.
- Empty leaderboard: verify the selected directory contains `playerdb*`.
- Shelve files fail across OS/Python versions: restore a compatible backup or
  migrate through an exported snapshot rather than modifying files in place.

## See Also

- `authentication.md`
- `data-safety.md`
- `phone-api.md`
