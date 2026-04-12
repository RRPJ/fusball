# Development Setup

This document describes how to set up and run the project on modern developer machines.

## Supported Baseline

- Python: 3.14 preferred on Windows; 3.11+ supported baseline
- OS: Windows 11 and Ubuntu 22.04+ (headless CI uses Ubuntu)

Python package note:

- Python 3.14 on Windows uses `pygame-ce` (selected automatically from `requirements.txt`).
- Python 3.13 and older use `pygame`.

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

The smoke check validates ranking-related logic and shelve compatibility assumptions without opening the Pygame UI.

```bash
python scripts/smoke_check.py
```

## 3) Choose A Runtime Flow

After setup, choose one of the two supported runtime flows.

### 3A) Touch-Screen Kiosk Flow

```bash
cd app
python fusball.py
```

Backward compatibility note:
- `python lcars.py` still works and currently delegates to the same app startup path.

Notes:
- The app is fullscreen and designed for touchscreen kiosks.
- In development, mouse cursor behavior is controlled by `DEV_MODE` in `app/config.py`.

### 3B) Mobile API Flow (Preferred)

Preferred production phone API service flow is manual and double-click driven:

- Start production phone API (prompts token): `start_phone_api_service.bat`
- Stop production phone API (also closes the Tailscale app): `stop_phone_api_service.bat`
- Check Tailscale/watchdog/API status: `status_phone_api_service.bat`

Behavior notes:

- Start ensures the Windows Tailscale service is running, opens the Tailscale app when installed, then performs a production backup before launching.
- A watchdog process keeps the phone API service running and restarts it after repeated `/health` failures.
- Stop shuts down the watchdog, phone API, and Tailscale app process, but does not disable or uninstall the Windows Tailscale service.
- Production writes target `app/` data; development flow remains `run_phone_api_dev.bat` with `sandbox/dev-data`.

Primary mobile URL:

- `http://<host>:8080/phone`

## 4) Coding Standards

Install development dependencies:

```bash
pip install -r requirements-dev.txt
```

Run lint and formatting checks:

```bash
ruff check app/startup.py app/fusball.py scripts
black --check app/startup.py app/fusball.py scripts
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

- If audio causes startup issues, keep `SOUND = False` in `app/config.py`.
- If you see display issues on desktop, validate fullscreen support at your current resolution.
- If shelve files fail to open across OS boundaries, restore from backup and re-seed/migrate data before use.

