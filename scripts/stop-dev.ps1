# Stops FastAPI backend and Next.js frontend started by start-dev.ps1
# Usage: ./scripts/stop-dev.ps1

param(
  [switch]$Aggressive
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'

$Root = Resolve-Path (Join-Path $PSScriptRoot '..')
$RunDir = Join-Path $Root 'run'

function Stop-Tree($procId) {
  if (-not $procId) { return }
  try {
    # Kill full tree (Windows)
    & taskkill /PID $procId /T /F | Out-Null
  } catch {
    try { Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue } catch {}
  }
}

function Stop-Guess($name, $pattern) {
  try {
    # Heuristic: find processes by command line containing pattern (uvicorn/next)
    $procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like $pattern }
    foreach ($p in $procs) {
      Write-Host "Heuristic stop $name (PID $($p.ProcessId))..." -ForegroundColor Yellow
      Stop-Tree $p.ProcessId
    }
  } catch {}
}

function Stop-FromPidFile($name, $pidPath, $pattern) {
  if (Test-Path $pidPath) {
    try {
      $procId = Get-Content -Path $pidPath -ErrorAction Stop | Select-Object -First 1
      if ($procId) {
        # Verify process command line matches expected pattern before killing
        $procInfo = $null
        try { $procInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" } catch {}
        if ($procInfo -and $procInfo.CommandLine -like $pattern) {
          Write-Host "Stopping $name (PID $procId)..." -ForegroundColor Yellow
          Stop-Tree $procId
        } else {
          Write-Host "PID $procId for $name does not match expected pattern; skipping." -ForegroundColor DarkYellow
        }
      }
    } catch {}
    try { Remove-Item -Force $pidPath -ErrorAction SilentlyContinue } catch {}
  } else {
    Write-Host "$name PID file not found: $pidPath" -ForegroundColor DarkGray
  }
}

Stop-FromPidFile -name 'Backend' -pidPath (Join-Path $RunDir 'backend.pid') -pattern '*uvicorn*src.orchestrator.api.main*'
Stop-FromPidFile -name 'Frontend' -pidPath (Join-Path $RunDir 'frontend.pid') -pattern '*next*dev*'

if ($Aggressive) {
  # Heuristic fallback if the PID files were missing or processes survived
  Stop-Guess -name 'Backend' -pattern '*uvicorn*src.orchestrator.api.main*'
  Stop-Guess -name 'Frontend' -pattern '*next*dev*'
}

Write-Host 'Stopped dev processes (if running).' -ForegroundColor Green
