@echo off
setlocal ENABLEEXTENSIONS

REM Resolve repository root from this script location.
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "APP_DIR=%ROOT%\app"
set "VENV_PY=%ROOT%\.venv\Scripts\python.exe"

if not exist "%APP_DIR%\lcars.py" (
    echo ERROR: Could not find app\lcars.py. Run this launcher from the repository root.
    pause
    exit /b 1
)

if not exist "%VENV_PY%" (
    echo Creating virtual environment in .venv ...
    py -3.14 -m venv "%ROOT%\.venv"
    if errorlevel 1 (
        echo ERROR: Failed to create .venv using Python 3.14.
        pause
        exit /b 1
    )

    echo Installing dependencies ...
    "%VENV_PY%" -m pip install --upgrade pip
    if errorlevel 1 (
        echo ERROR: Failed to upgrade pip.
        pause
        exit /b 1
    )

    "%VENV_PY%" -m pip install -r "%ROOT%\requirements.txt"
    if errorlevel 1 (
        echo ERROR: Failed to install dependencies.
        pause
        exit /b 1
    )
)

if defined FUSBALL_NO_LAUNCH (
    echo Setup check complete. Skipping app launch because FUSBALL_NO_LAUNCH is set.
    exit /b 0
)

cd /d "%APP_DIR%"
"%VENV_PY%" lcars.py
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo App exited with error code %EXIT_CODE%.
    pause
)

exit /b %EXIT_CODE%
