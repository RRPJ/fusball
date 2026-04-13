@echo off
setlocal

set "ROOT=%~dp0"
PowerShell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\phone_stack_control.ps1" stop

if errorlevel 1 (
  echo.
  echo Failed to stop phone API service.
) else (
  echo.
  echo Phone API service stop command completed.
)

echo.
pause
