@echo off
setlocal
REM Stop Docker Compose stack (backend + frontend)
pushd "%~dp0.."
docker compose down
popd
