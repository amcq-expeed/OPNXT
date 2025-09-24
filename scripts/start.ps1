# Unified start script: chooses Docker Compose if available, otherwise local dev
# Usage: ./scripts/start.ps1  (or double-click scripts/start.bat)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Root = Resolve-Path (Join-Path $PSScriptRoot '..')
$ComposeFile = Join-Path $Root 'docker-compose.yml'

function Test-Cmd($name) {
  try { Get-Command $name -ErrorAction Stop | Out-Null; return $true } catch { return $false }
}

function Test-DockerEngine() {
  if (-not (Test-Cmd 'docker')) { return $false }
  $out = [System.IO.Path]::GetTempFileName()
  $err = [System.IO.Path]::GetTempFileName()
  try {
    $p = Start-Process -FilePath 'docker' -ArgumentList 'info --format "{{json .}}"' -NoNewWindow -Wait -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
    return ($p.ExitCode -eq 0)
  } catch {
    return $false
  } finally {
    try { Remove-Item -ErrorAction SilentlyContinue $out, $err } catch {}
  }
}

Write-Host "OPNXT Start" -ForegroundColor Cyan

$hasDocker = Test-DockerEngine
$hasComposeFile = Test-Path $ComposeFile

if ($hasDocker -and $hasComposeFile) {
  Write-Host "Detected Docker. Starting via Docker Compose..." -ForegroundColor Green
  Push-Location $Root
  try {
    # Non-blocking browser open
    Start-Job -ScriptBlock { Start-Sleep -Seconds 3; Start-Process 'http://localhost:3000/dashboard' } | Out-Null
    docker compose up --build
  } finally {
    Pop-Location
  }
}
else {
  Write-Host "Docker not available or compose file missing. Starting local dev..." -ForegroundColor Yellow
  & (Join-Path $PSScriptRoot 'start-dev.ps1')
}
