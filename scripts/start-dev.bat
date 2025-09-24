@echo off
setlocal
REM Start local dev (FastAPI + Next.js) using PowerShell script
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-dev.ps1"
