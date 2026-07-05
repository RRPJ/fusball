# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Read First

- `README.md` — project overview, entrypoints, quick start
- `docs/architecture.md` — runtime model, module boundaries, persistence
- `docs/development.md` — setup, lint/format commands, run modes, troubleshooting
- `docs/phone-api.md` — endpoint reference, auth model, env vars
- `docs/phone-write-policy.md` — write scope, conflict rules, validation
- `docs/data-safety.md` — backup/restore procedures, migration notes
- `.github/copilot-instructions.md` — editing rules, verification baseline, data safety rules

## Repository Overview

Fusball is a phone-first foosball match and leaderboard service. It tracks player skill separately for offense and defense using TrueSkill and exposes both a browser UI (`/phone`) and JSON endpoints (`/api/*`) from the same runtime.

**Single runtime:** `app/phone_api.py` (Flask). `api/index.py` re-exports the same app factory for Vercel deployments.

**Stateful data:** Python `shelve` files under `app/` — `playerdb*`, `recentplayers*`, `match_history*`. Treat as production-like. A text audit log (`logfile.log`) is also maintained.

## Quick Commands

```bash
# Setup
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt  # includes prod + dev deps

# Smoke check (ranking logic + shelve compatibility)
python scripts/smoke_check.py

# Run the phone API locally
cd app && python phone_api.py

# Lint and format
ruff check app api test_*.py scripts
black --check app api test_*.py scripts

# Tests (unittest-based, run individually)
python -m unittest test_phone_api.py     # phone/API regression
python -m unittest test_match_flow.py    # match/ranking flow
python -m unittest test_integration.py   # integration checks

# Pre-commit hooks
pre-commit install
```

## Non-Obvious Facts

- **Phone UI is embedded:** HTML/CSS/JS for `/phone` lives inline in `app/phone_api.py` (118KB file).
- **Offense-first ordering:** Internal doubles/team math uses `[offense, defense]` ordering. The phone UI renders as `Defense + Offense`. Do not change internal order without checking phone/history behavior.
- **Split PIN auth:** Read endpoints accept `X-Read-Pin` or writer PIN. Write endpoints require `X-Write-Pin`. Legacy `X-Operator-Token` fallback is still supported when `WRITE_PIN_HASH` is not configured.
- **Write lock:** Short-lived file lock (`phone_api_write.lock`) prevents concurrent writes. Returns `409 Conflict` on collision.
- **Duplicate detection:** Match submits within a 60-second window are rejected as duplicates.
- **Dev vs prod data:** Dev scripts write to `sandbox/dev-data`. Production writes to `app/`. Override with `FUSBALL_PHONE_API_DB_DIR`.
- **Presence is ephemeral:** Player presence is session-scoped server state, lost on restart.
- **Neon migration in progress:** Shelve is the current local store; Neon-backed persistence is the convergence target for hosted deployments.

## Service Layer

Core domain services under `app/services/`:
- `match_service.py` — odds, rating updates, lineup balancing
- `match_history.py` — structured match-history append/query/replay
- `match_log.py` — legacy text audit log
- `phone_write_store.py` — write-path persistence helpers
- `player_store.py` — ranking helpers, player list utilities

Support: `app/odds.py` (win probability, player level, rank string), `app/startup.py` (diagnostics), `app/dbmigration.py` (schema upgrades).

## Editing Rules (from copilot-instructions.md)

- Keep logic changes localized; avoid unrelated formatting churn.
- Indentation mistakes are a recurring regression source — check carefully.
- Add comments only when intent is not obvious.
- Use clear names and small helpers for ranking, persistence, and transforms.

## Data Safety (non-negotiable)

- **Always** run `python scripts/backup_state.py` before changing persistence logic, migrations, or data-shape assumptions.
- Prefer additive migrations over destructive rewrites.
- Document migration and rollback impact in `docs/data-safety.md` when behavior changes.
- Never mutate shelve schema casually.

## Verification Checklist

After making changes, run the smallest verification that covers the affected path:

| Change Type | Verification |
|---|---|
| Phone runtime / UI edits | `python -m unittest test_phone_api.py` |
| Match/ranking logic | `python -m unittest test_match_flow.py` |
| Persistence / services | `python scripts/smoke_check.py` + `python -m unittest test_integration.py` |
| General smoke | `python scripts/smoke_check.py` |
| Auth flow | `python scripts/smoke_phone_api_auth.py` |

## Docs to Update

If request handling, operator workflow, API contract, or migration expectations change, update `README.md` and the relevant `docs/` files before committing.
