# Unified stop script: stops Docker Compose if running, then local dev processes
# Usage: ./scripts/stop.ps1  (or double-click scripts/stop.bat)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'

$Root = Resolve-Path (Join-Path $PSScriptRoot '..')
$ComposeFile = Join-Path $Root 'docker-compose.yml'

function Test-Cmd($name) {
  try { Get-Command $name -ErrorAction Stop | Out-Null; return $true } catch { return $false }
}

function Test-DockerEngine() {
  if (-not (Test-Cmd 'docker')) { return $false }
  try { docker info --format '{{json .}}' | Out-Null; return $true } catch { return $false }
}

$hasDocker = Test-DockerEngine
$hasComposeFile = Test-Path $ComposeFile

if ($hasDocker -and $hasComposeFile) {
  Write-Host 'Stopping Docker Compose stack...' -ForegroundColor Yellow
  Push-Location $Root
  try { docker compose down } catch {}
  Pop-Location
}

# Always try to stop local dev PIDs as well
& (Join-Path $PSScriptRoot 'stop-dev.ps1')

Write-Host 'Stop sequence completed.' -ForegroundColor Green
