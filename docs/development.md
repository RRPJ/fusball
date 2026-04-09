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
python fusball.py
```

Backward compatibility note:
- `python lcars.py` still works and currently delegates to the same app startup path.

Notes:
- The app is fullscreen and designed for touchscreen kiosks.
- In development, mouse cursor behavior is controlled by `DEV_MODE` in `app/config.py`.

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

Function documentation tip:
- The inline function documentation you asked about is called a `docstring`.
- For new or changed functions, prefer short docstrings that describe purpose, inputs, and return value.

## 5) Troubleshooting

- If audio causes startup issues, keep `SOUND = False` in `app/config.py`.
- If you see display issues on desktop, validate fullscreen support at your current resolution.
- If shelve files fail to open across OS boundaries, restore from backup and re-seed/migrate data before use.
