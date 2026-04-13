@echo off
setlocal

set "ROOT=%~dp0"
PowerShell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\run_phone_api_prod.ps1"
