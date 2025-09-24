# Starts FastAPI backend and Next.js frontend for local dev
# Usage: ./scripts/start-dev.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Repo root (scripts/..)
$Root = Resolve-Path (Join-Path $PSScriptRoot '..')
$RunDir = Join-Path $Root 'run'
if (-not (Test-Path $RunDir)) { New-Item -ItemType Directory -Path $RunDir | Out-Null }

function Test-Cmd($name) {
  try { Get-Command $name -ErrorAction Stop | Out-Null; return $true } catch { return $false }
}

Write-Host "Starting OPNXT dev environment..." -ForegroundColor Cyan

# Ensure backend deps (python + uvicorn)
if (-not (Test-Cmd 'python')) { throw 'python is not on PATH. Install Python 3.12+ and retry.' }

# Install Python dependencies
Write-Host 'Ensuring backend Python dependencies...' -ForegroundColor Yellow
Push-Location $Root
try {
  & python -m pip install -r requirements.txt | Write-Host
} finally {
  Pop-Location
}

# Start backend (FastAPI)
$backendArgs = @('-m','uvicorn','src.orchestrator.api.main:app','--host','0.0.0.0','--port','8000','--reload')
$backend = Start-Process -FilePath 'python' -ArgumentList $backendArgs -WorkingDirectory $Root -PassThru -WindowStyle Minimized
$backend.Id | Out-File -FilePath (Join-Path $RunDir 'backend.pid') -Encoding ascii -Force

# Prepare frontend env
$FrontendDir = Join-Path $Root 'frontend'
if (-not (Test-Path $FrontendDir)) { throw "Frontend directory not found: $FrontendDir" }
$envFile = Join-Path $FrontendDir '.env.local'
$envExample = Join-Path $FrontendDir '.env.local.example'
if (-not (Test-Path $envFile) -and (Test-Path $envExample)) { Copy-Item $envExample $envFile -Force }

# Ensure Node
if (-not (Test-Cmd 'npm')) { throw 'npm is not on PATH. Install Node.js 18+ and retry.' }

# Install deps if node_modules missing, or if critical dev deps like tailwindcss are not present
$NodeModulesDir = Join-Path $FrontendDir 'node_modules'
$TailwindDir = Join-Path $NodeModulesDir 'tailwindcss'
if (-not (Test-Path $NodeModulesDir) -or -not (Test-Path $TailwindDir)) {
  Write-Host 'Installing/updating frontend dependencies...' -ForegroundColor Yellow
  & npm --prefix $FrontendDir install | Write-Host
}

# Start frontend (Next.js)
$frontend = Start-Process -FilePath 'npm' -ArgumentList @('--prefix',$FrontendDir,'run','dev') -WorkingDirectory $FrontendDir -PassThru -WindowStyle Minimized
$frontend.Id | Out-File -FilePath (Join-Path $RunDir 'frontend.pid') -Encoding ascii -Force

Write-Host ''
Write-Host 'OPNXT dev environment started.' -ForegroundColor Green
Write-Host 'Backend:  http://localhost:8000/health'
Write-Host 'Frontend: http://localhost:3000/dashboard'
Write-Host ''
Write-Host 'To stop:  ./scripts/stop-dev.ps1' -ForegroundColor DarkYellow

# Try to open the browser to the frontend after a brief delay
Start-Sleep -Seconds 2
try { Start-Process 'http://localhost:3000/dashboard' } catch {}
