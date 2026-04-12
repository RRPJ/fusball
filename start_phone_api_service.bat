@echo off
setlocal

set "ROOT=%~dp0"
PowerShell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\phone_stack_control.ps1" start -PromptToken

if errorlevel 1 (
  echo.
  echo Failed to start phone API service.
) else (
  echo.
  echo Phone API service start command completed.
)

echo.
pause
