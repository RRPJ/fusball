# Development Setup

This document describes how to set up and run the project on modern developer machines.

## Supported Baseline

- Python: 3.11+ supported baseline
- OS: Windows 11 and Ubuntu 22.04+ (headless CI uses Ubuntu)

## 1) Create a Virtual Environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Windows PowerShell (explicit Python 3.14):

```powershell
py -3.14 -m venv .venv314
.\.venv314\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 2) Run Smoke Check

The smoke check validates ranking-related logic and shelve compatibility assumptions for the phone API workflow.

```bash
python scripts/smoke_check.py
```

## 3) Run The Phone API

Preferred production phone API service flow is manual and double-click driven:

- Start production phone API (prompts writer PIN): `start_phone_api_service.bat`
- Stop production phone API: `stop_phone_api_service.bat`
- Check watchdog/API status: `status_phone_api_service.bat`

Behavior notes:

- Start performs a production backup before launching.
- A watchdog process keeps the phone API service running and restarts it after repeated `/health` failures.
- Stop shuts down the watchdog and phone API process.
- Production writes target `app/` data; development flow remains `run_phone_api_dev.bat` with `sandbox/dev-data`.

Primary mobile URL:

- `http://<host>:8080/phone`

Split auth testing in DEV mode:

- Generate hashes manually:

```bash
python scripts/generate_pin_hash.py --read-pin read1234 --write-pin write5678 --format dotenv
```

- Start dev API with prompted split PINs:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File scripts/run_phone_api_dev.ps1 -PromptPins
```

- Start dev API with explicit split PINs:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File scripts/run_phone_api_dev.ps1 -ReadPin "read1234" -WritePin "write5678"
```

Notes:
- `run_phone_api_dev.bat` still works and calls the same script.
- If split PINs are not provided and no PIN hashes are configured, the script falls back to legacy token mode.

Direct local run:

```bash
cd app
python phone_api.py
```

Staging/production auth smoke checks:

```bash
python scripts/smoke_phone_api_auth.py --base-url https://<your-deployment-host> --expect-auth --read-pin <read-pin> --write-pin <write-pin>
```

Neon parity smoke check (before cutover):

```bash
python scripts/smoke_neon_parity.py --db-dir app --database-url <database-url> --mode strict
```

Use `--mode counts` when you only want fast count-level verification.

Full cutover sequence:
- See `docs/priority-0-cutover-runbook.md` for the ordered staging and production checklist.

Recommended environment model:
- Vercel Production -> Neon Production
- Vercel Preview -> Neon Preview
- Local coding -> local shelve sandbox unless cloud-like testing is needed

Legacy-token fallback smoke check:

```bash
python scripts/smoke_phone_api_auth.py --base-url http://127.0.0.1:8080 --operator-token <token>
```

## 4) Coding Standards

Install development dependencies:

```bash
pip install -r requirements-dev.txt
```

Run lint and formatting checks:

```bash
ruff check app api test_*.py scripts
black --check app api test_*.py scripts
```

Enable pre-commit hooks:

```bash
pre-commit install
```

Hook configuration lives in `.pre-commit-config.yaml`.

Function documentation tip:
- The inline function documentation you asked about is called a `docstring`.
- For new or changed functions, prefer short docstrings that describe purpose, inputs, and return value.

## 5) Troubleshooting

- If the phone API cannot write, verify `READ_PIN_HASH` / `WRITE_PIN_HASH` or the legacy token fallback configuration.
- If the service starts but the phone page is empty, verify the selected data directory contains `playerdb*` and related state.
- If shelve files fail to open across OS boundaries, restore from backup and re-seed/migrate data before use.

