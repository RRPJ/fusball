@echo off
setlocal

set "ROOT=%~dp0"
PowerShell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\phone_stack_control.ps1" status

if errorlevel 1 (
  echo.
  echo Failed to read phone API service status.
)

echo.
pause
