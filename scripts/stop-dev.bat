@echo off
setlocal
REM Stop local dev (FastAPI + Next.js) using PowerShell script
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-dev.ps1"
