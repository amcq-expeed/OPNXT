@echo off
setlocal
REM Start Docker Compose stack (backend + frontend)
pushd "%~dp0.."
docker compose up --build
popd
