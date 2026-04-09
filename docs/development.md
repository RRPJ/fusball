# Development Setup

This document describes how to set up and run the project on modern developer machines.

## Supported Baseline

- Python: 3.11
- OS: Windows 11 and Ubuntu 22.04+ (headless CI uses Ubuntu)

Additional supported path:

- Python 3.14 on Windows is supported using `pygame-ce` (selected automatically from `requirements.txt`).

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

## 3) Run the Application

```bash
cd app
python lcars.py
```

Notes:
- The app is fullscreen and designed for touchscreen kiosks.
- In development, mouse cursor behavior is controlled by `DEV_MODE` in `app/config.py`.

## 4) Troubleshooting

- If audio causes startup issues, keep `SOUND = False` in `app/config.py`.
- If you see display issues on desktop, validate fullscreen support at your current resolution.
- If shelve files fail to open across OS boundaries, restore from backup and re-seed/migrate data before use.
