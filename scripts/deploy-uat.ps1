# Deploy OPNXT to a Windows host
# Requires: administrative PowerShell, robocopy, Node.js, npm, and Python available on the PATH.
# Optional: IIS WebAdministration module and Windows services (e.g., nssm) named for frontend/backed.

[CmdletBinding()]
param(
    [string]$SourceRoot,
    [string]$TargetRoot = "C:\opnxt",
    [string]$BackendEnvPath,
    [string]$FrontendEnvPath,
    [string]$BackendServiceName = "opnxt-backend",
    [string]$FrontendServiceName = "opnxt-frontend",
    [string]$SiteName = "opnxt"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not $SourceRoot) {
    $SourceRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
} else {
    $SourceRoot = Resolve-Path $SourceRoot
}

Write-Host "Deploying OPNXT from $SourceRoot to $TargetRoot" -ForegroundColor Cyan

function Stop-ServiceIfExists {
    param([string]$Name)
    if ([string]::IsNullOrWhiteSpace($Name)) { return }
    $svc = Get-Service -Name $Name -ErrorAction SilentlyContinue
    if ($null -ne $svc) {
        if ($svc.Status -ne 'Stopped') {
            Write-Host "Stopping service $Name" -ForegroundColor Yellow
            Stop-Service -Name $Name -Force -ErrorAction Stop
            $svc.WaitForStatus('Stopped', '00:00:30')
        }
    } else {
        Write-Host "Service $Name not found, skipping stop" -ForegroundColor DarkGray
    }
}

function Start-ServiceIfExists {
    param([string]$Name)
    if ([string]::IsNullOrWhiteSpace($Name)) { return }
    $svc = Get-Service -Name $Name -ErrorAction SilentlyContinue
    if ($null -ne $svc) {
        if ($svc.Status -ne 'Running') {
            Write-Host "Starting service $Name" -ForegroundColor Green
            Start-Service -Name $Name -ErrorAction Stop
            $svc.WaitForStatus('Running', '00:00:30')
        }
    } else {
        Write-Host "Service $Name not found, skipping start" -ForegroundColor DarkGray
    }
}

 $iisAccessible = $false
 if (-not [string]::IsNullOrWhiteSpace($SiteName)) {
     $webModule = Get-Module -ListAvailable -Name WebAdministration | Select-Object -First 1
     if ($null -ne $webModule) {
         try {
            Import-Module WebAdministration -ErrorAction Stop
            $site = $null
            try {
                $site = Get-Website -Name $SiteName -ErrorAction Stop
                $iisAccessible = $true
            } catch [System.UnauthorizedAccessException] {
                Write-Warning ("Unable to manage IIS site {0} due to insufficient permissions. Continuing without recycling the site." -f $SiteName)
            } catch {
                Write-Warning ("Unable to read IIS site {0}: {1}" -f $SiteName, $_.Exception.Message)
            }
            if ($iisAccessible -and $null -ne $site -and $site.state -ne 'Stopped') {
                Write-Host ("Stopping IIS site {0}" -f $SiteName) -ForegroundColor Yellow
                Stop-Website -Name $SiteName
            }
         } catch {
             Write-Warning "Failed to import WebAdministration module: $($_.Exception.Message)"
             $importedWebModule = $false
         }
{{ ... }}
     }
 }

Stop-ServiceIfExists -Name $FrontendServiceName
Stop-ServiceIfExists -Name $BackendServiceName

if (-not (Test-Path $TargetRoot)) {
    Write-Host "Creating target directory $TargetRoot" -ForegroundColor Cyan
    New-Item -ItemType Directory -Path $TargetRoot | Out-Null
}

$excludeDirs = @('.git', '.github', 'tests', 'run', '.venv', 'node_modules', '.next', '__pycache__', '.pytest_cache', '.mypy_cache')
$excludeFiles = @('.env', '.env.local', '.env.production', '.env.deploy', 'frontend/.env.deploy')

$robocopyArgs = @()
$robocopyArgs += '"{0}"' -f $SourceRoot
$robocopyArgs += '"{0}"' -f $TargetRoot
$robocopyArgs += '/MIR'
foreach ($dir in $excludeDirs) {
    $robocopyArgs += '/XD'
    $robocopyArgs += '"{0}"' -f (Join-Path $SourceRoot $dir)
}
foreach ($file in $excludeFiles) {
    $robocopyArgs += '/XF'
    $robocopyArgs += $file
}
$robocopyArgs += '/COPY:DAT'
$robocopyArgs += '/R:2'
$robocopyArgs += '/W:5'

Write-Host "Syncing files to $TargetRoot" -ForegroundColor Cyan
$robocopyProcess = Start-Process -FilePath 'robocopy' -ArgumentList $robocopyArgs -NoNewWindow -Wait -PassThru
$rc = $robocopyProcess.ExitCode
if ($rc -ge 8) {
    throw "robocopy failed with exit code $rc"
}

if ($BackendEnvPath -and (Test-Path $BackendEnvPath)) {
    Write-Host "Applying backend environment file to $TargetRoot\\.env" -ForegroundColor Cyan
    Copy-Item -Path $BackendEnvPath -Destination (Join-Path $TargetRoot '.env') -Force
}

if ($FrontendEnvPath -and (Test-Path $FrontendEnvPath)) {
    $frontendEnvTarget = Join-Path $TargetRoot 'frontend/.env.production'
    Write-Host "Applying frontend environment file to $frontendEnvTarget" -ForegroundColor Cyan
    Copy-Item -Path $FrontendEnvPath -Destination $frontendEnvTarget -Force
}

Push-Location $TargetRoot
try {
    $pythonExe = Get-Command python -ErrorAction Stop | Select-Object -ExpandProperty Source
    $nodeExe = Get-Command node -ErrorAction Stop | Select-Object -ExpandProperty Source
    Write-Host "Python resolved to $pythonExe" -ForegroundColor DarkGray
    Write-Host "Node resolved to $nodeExe" -ForegroundColor DarkGray

    $venvPath = Join-Path $TargetRoot '.venv'
    if (Test-Path $venvPath) {
        Write-Host "Removing existing Python virtual environment" -ForegroundColor DarkGray
        Remove-Item -Path $venvPath -Recurse -Force
    }
    Write-Host "Creating Python virtual environment" -ForegroundColor Cyan
    python -m venv $venvPath
    & (Join-Path $venvPath 'Scripts\python.exe') -m pip install --upgrade pip
    & (Join-Path $venvPath 'Scripts\pip.exe') install -r (Join-Path $TargetRoot 'requirements.txt')
    $apiReq = Join-Path $TargetRoot 'requirements.api.txt'
    if (Test-Path $apiReq) {
        & (Join-Path $venvPath 'Scripts\pip.exe') install -r $apiReq
    }

    $frontendPath = Join-Path $TargetRoot 'frontend'
    if (Test-Path $frontendPath) {
        Push-Location $frontendPath
        try {
            Write-Host "Installing frontend dependencies" -ForegroundColor Cyan
            npm ci --omit=dev
            Write-Host "Building Next.js frontend" -ForegroundColor Cyan
            npm run build
        }
        finally {
            Pop-Location
        }
    } else {
        Write-Warning "Frontend directory not found at $frontendPath"
    }
}
finally {
    Pop-Location
}

Start-ServiceIfExists -Name $BackendServiceName
Start-ServiceIfExists -Name $FrontendServiceName

 if ($importedWebModule -and $iisAccessible -and -not [string]::IsNullOrWhiteSpace($SiteName)) {
     try {
         $site = Get-Website -Name $SiteName -ErrorAction Stop
         Write-Host ("Starting IIS site {0}" -f $SiteName) -ForegroundColor Green
         Start-Website -Name $SiteName
     } catch [System.UnauthorizedAccessException] {
         Write-Warning ("Insufficient permissions to start IIS site {0}. Please recycle manually." -f $SiteName)
     } catch {
         Write-Warning ("Failed to start IIS site {0}: {1}" -f $SiteName, $_.Exception.Message)
     }
 }

Write-Host 'Deployment completed successfully.' -ForegroundColor Green
