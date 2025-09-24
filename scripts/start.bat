@echo off
setlocal
REM Unified start: prefers Docker Compose if available, else local dev
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
