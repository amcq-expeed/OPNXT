# OPNXT - Developer & Tester Start Guide

This guide provides one-command startup for the OPNXT app (FastAPI backend + Next.js frontend).

The UI runs at: http://localhost:3000/projects
The API runs at: http://localhost:8000

## Option 0: One‑click Launcher (auto-detects Docker)

Fastest option for testers. From the repo root:

```
scripts/start.bat
```

This will prefer Docker Compose if Docker is available, otherwise it will fall back to local dev (Python + Node). To stop everything:

```
scripts/stop.ps1
```

If you prefer PowerShell directly:

```
./scripts/start.ps1
./scripts/stop.ps1
```

## Option A: Local (no Docker)

Prerequisites
- Windows PowerShell
- Python 3.12+ available as `python`
- Node.js 18+ available as `npm`

Start
```powershell
# From the repo root
./scripts/start-dev.ps1
```
What it does
- Installs Python deps via `requirements.txt`
- Starts FastAPI with Uvicorn at http://localhost:8000
- Copies `frontend/.env.local.example` to `.env.local` if missing
- Installs frontend deps (if missing)
- Starts Next.js dev server at http://localhost:3000 and opens your browser

Stop
```powershell
./scripts/stop-dev.ps1
```

## Option B: Docker Compose (one command)

Prerequisites
- Docker Desktop (with Docker Compose V2)

Run
```powershell
# From the repo root
docker compose up --build
```
- Backend available at http://localhost:8000 (with `/health` and `/metrics`)
- Frontend available at http://localhost:3000/projects
- Live code reload enabled via bind mounts

Stop
```powershell
docker compose down
```

## Troubleshooting
- Ports in use: Stop any process using 8000 or 3000, or change ports in `docker-compose.yml` or scripts.
- Node not found: Install Node.js 18+ and restart your terminal.
- Python not found: Install Python 3.12+, ensure `python` on PATH, and retry.
- PDF/WeasyPrint: PDF export is optional. The app runs even if WeasyPrint isn’t installed on Windows.
- CORS: Already enabled for `http://localhost:3000` in `src/orchestrator/api/main.py`.

## Directory Map
- Backend API: `src/orchestrator/api/main.py`
- Projects router: `src/orchestrator/api/routers/projects.py`
- State machine: `src/orchestrator/core/state_machine.py`
- Frontend app: `frontend/` (Next.js)
- Dev scripts: `scripts/start-dev.ps1`, `scripts/stop-dev.ps1`, `scripts/start.ps1`, `scripts/stop.ps1`, `scripts/start.bat`
- Compose: `docker-compose.yml`

## Next Steps (for Admins)
- Configure JWT/RBAC on the backend and wire login in the frontend.
- Add Playwright e2e tests and wire into CI.
- Deploy containers to your preferred environment (add a production compose or Helm chart).
