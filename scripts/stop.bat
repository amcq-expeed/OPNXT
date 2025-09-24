@echo off
setlocal
REM Unified stop: stops Docker Compose if running, then local dev PIDs
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop.ps1"
