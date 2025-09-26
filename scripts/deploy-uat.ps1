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
    [string]$SiteName = "opnxt",
    [string]$PythonExecutable,
    [string]$NodeExecutable
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

function Resolve-PythonExecutable {
    param([string]$PreferredPath)

    if ($PreferredPath) {
        if (Test-Path $PreferredPath) {
            Write-Host "Using python from provided path: $PreferredPath" -ForegroundColor DarkGray
            return (Resolve-Path $PreferredPath).ProviderPath
        } else {
            throw "Provided PythonExecutable path '$PreferredPath' does not exist."
        }
    }

    if ($env:PYTHON_EXECUTABLE) {
        $candidate = $env:PYTHON_EXECUTABLE
        if (Test-Path $candidate) {
            Write-Host "Using python from PYTHON_EXECUTABLE: $candidate" -ForegroundColor DarkGray
            return (Resolve-Path $candidate).ProviderPath
        } else {
            Write-Warning "PYTHON_EXECUTABLE environment variable set to '$candidate' but file not found."
        }
    }

    $commandPreference = @('python', 'python3')
    foreach ($name in $commandPreference) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) {
            Write-Host "Found python via Get-Command '$name': $($cmd.Source)" -ForegroundColor DarkGray
            return $cmd.Source
        }
    }

    try {
        $whereResults = & where.exe python 2>$null
        if ($whereResults) {
            foreach ($line in $whereResults -split "`n") {
                $trimmed = $line.Trim()
                if ($trimmed -and (Test-Path $trimmed)) {
                    Write-Host "Found python via where.exe: $trimmed" -ForegroundColor DarkGray
                    return $trimmed
                }
            }
        }
    } catch {
        Write-Host "where.exe did not resolve python: $($_.Exception.Message)" -ForegroundColor DarkGray
    }

    $pathScopes = @('Process','User','Machine')
    foreach ($scope in $pathScopes) {
        try {
            $pathValue = [System.Environment]::GetEnvironmentVariable('Path', $scope)
        } catch { $pathValue = $null }
        if (-not $pathValue) { continue }
        $pathEntries = $pathValue.Split(';') | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
        foreach ($entryRaw in $pathEntries) {
            $entry = $entryRaw.Trim().Trim('"')
            if ([string]::IsNullOrWhiteSpace($entry)) { continue }
            $candidate = Join-Path $entry 'python.exe'
            if (Test-Path $candidate) {
                $resolved = (Resolve-Path $candidate).ProviderPath
                Write-Host "Found python via PATH ($scope): $resolved" -ForegroundColor DarkGray
                return $resolved
            }
        }
    }

    if ($env:PYTHONHOME) {
        $candidate = Join-Path $env:PYTHONHOME 'python.exe'
        if (Test-Path $candidate) {
            $resolvedHome = (Resolve-Path $candidate).ProviderPath
            Write-Host "Using python from PYTHONHOME: $resolvedHome" -ForegroundColor DarkGray
            return $resolvedHome
        }
    }

    $pyLauncher = Get-Command 'py' -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        try {
            $launcherPath = & $pyLauncher.Source -3 -c "import sys, pathlib; print(pathlib.Path(sys.executable).resolve())" 2>$null
            if ($launcherPath -and (Test-Path $launcherPath)) {
                Write-Host "Using python via launcher 'py': $launcherPath" -ForegroundColor DarkGray
                return $launcherPath
            }
        } catch {
            Write-Host "Python launcher detected but unable to resolve interpreter: $($_.Exception.Message)" -ForegroundColor DarkGray
        }
    }

    $knownPaths = @(
        "$env:ProgramFiles\Python312\python.exe",
        "$env:ProgramFiles\Python311\python.exe",
        "$env:ProgramFiles\Python310\python.exe",
        "$env:LocalAppData\Programs\Python\Python312\python.exe",
        "$env:LocalAppData\Programs\Python\Python311\python.exe",
        "$env:LocalAppData\Programs\Python\Python310\python.exe"
    ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }

    foreach ($path in $knownPaths) {
        if (Test-Path $path) {
            $resolvedKnown = (Resolve-Path $path).ProviderPath
            Write-Host "Found python via known path list: $resolvedKnown" -ForegroundColor DarkGray
            return $resolvedKnown
        }
    }

    try {
        $regInstalls = Get-ChildItem 'HKLM:\SOFTWARE\Python\PythonCore' -ErrorAction Stop | ForEach-Object {
            $ip = Join-Path $_.PSPath 'InstallPath'
            try { (Get-ItemProperty $ip -Name '(default)' -ErrorAction Stop).'(default)' } catch { $null }
        } | Where-Object { $_ }

        foreach ($installPath in $regInstalls) {
            $exe = Join-Path $installPath 'python.exe'
            if (Test-Path $exe) { return $exe }
        }
    } catch {
        Write-Host "No python install found via registry lookup: $($_.Exception.Message)" -ForegroundColor DarkGray
    }

    try {
        $userPython = Get-ChildItem -Path 'C:\Users' -Filter python.exe -ErrorAction Stop -Recurse |
            Sort-Object FullName -Descending |
            Select-Object -First 1
        if ($userPython -and (Test-Path $userPython.FullName)) {
            $resolvedUser = (Resolve-Path $userPython.FullName).ProviderPath
            Write-Host "Found python under C:\Users: $resolvedUser" -ForegroundColor DarkGray
            return $resolvedUser
        }
    } catch {
        Write-Host "Unable to discover python.exe under C:\Users: $($_.Exception.Message)" -ForegroundColor DarkGray
    }

    try {
        $toolCache = Get-ChildItem -Path 'C:\hostedtoolcache\windows\Python' -Recurse -Filter python.exe -ErrorAction Stop |
            Sort-Object FullName -Descending |
            Select-Object -First 1
        if ($toolCache -and (Test-Path $toolCache.FullName)) {
            $resolvedCache = (Resolve-Path $toolCache.FullName).ProviderPath
            Write-Host "Found python via hostedtoolcache: $resolvedCache" -ForegroundColor DarkGray
            return $resolvedCache
        }
    } catch {
        Write-Host "No python.exe discovered in hostedtoolcache: $($_.Exception.Message)" -ForegroundColor DarkGray
    }

    throw 'Unable to locate python executable. Ensure Python 3 is installed and available on PATH for the deployment account.'
}

function Resolve-NodeExecutable {
    param([string]$PreferredPath)

    if ($PreferredPath) {
        if (Test-Path $PreferredPath) {
            Write-Host "Using node from provided path: $PreferredPath" -ForegroundColor DarkGray
            return (Resolve-Path $PreferredPath).ProviderPath
        } else {
            throw "Provided NodeExecutable path '$PreferredPath' does not exist."
        }
    }

    if ($env:NODE_EXECUTABLE) {
        $candidate = $env:NODE_EXECUTABLE
        if (Test-Path $candidate) {
            Write-Host "Using node from NODE_EXECUTABLE: $candidate" -ForegroundColor DarkGray
            return (Resolve-Path $candidate).ProviderPath
        } else {
            Write-Warning "NODE_EXECUTABLE environment variable set to '$candidate' but file not found."
        }
    }

    $commandPreference = @('node', 'node.exe')
    foreach ($name in $commandPreference) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) {
            Write-Host "Found node via Get-Command '$name': $($cmd.Source)" -ForegroundColor DarkGray
            return $cmd.Source
        }
    }

    try {
        $whereResults = & where.exe node 2>$null
        if ($whereResults) {
            foreach ($line in $whereResults -split "`n") {
                $trimmed = $line.Trim()
                if ($trimmed -and (Test-Path $trimmed)) {
                    Write-Host "Found node via where.exe: $trimmed" -ForegroundColor DarkGray
                    return (Resolve-Path $trimmed).ProviderPath
                }
            }
        }
    } catch {
        Write-Host "where.exe did not resolve node: $($_.Exception.Message)" -ForegroundColor DarkGray
    }

    $pathScopes = @('Process','User','Machine')
    foreach ($scope in $pathScopes) {
        try {
            $pathValue = [System.Environment]::GetEnvironmentVariable('Path', $scope)
        } catch { $pathValue = $null }
        if (-not $pathValue) { continue }
        $pathEntries = $pathValue.Split(';') | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
        foreach ($entryRaw in $pathEntries) {
            $entry = $entryRaw.Trim().Trim('"')
            if ([string]::IsNullOrWhiteSpace($entry)) { continue }
            $candidate = Join-Path $entry 'node.exe'
            if (Test-Path $candidate) {
                $resolved = (Resolve-Path $candidate).ProviderPath
                Write-Host "Found node via PATH ($scope): $resolved" -ForegroundColor DarkGray
                return $resolved
            }
        }
    }

    $programFiles = @()
    if ($env:ProgramFiles) { $programFiles += $env:ProgramFiles }
    if (${env:ProgramFiles(x86)}) { $programFiles += ${env:ProgramFiles(x86)} }
    if ($env:LOCALAPPDATA) { $programFiles += (Join-Path $env:LOCALAPPDATA 'Programs') }

    foreach ($root in $programFiles | Sort-Object -Unique) {
        $nodeDir = Join-Path $root 'nodejs'
        $candidate = Join-Path $nodeDir 'node.exe'
        if (Test-Path $candidate) {
            $resolvedKnown = (Resolve-Path $candidate).ProviderPath
            Write-Host "Found node in nodejs directory: $resolvedKnown" -ForegroundColor DarkGray
            return $resolvedKnown
        }
    }

    if ($env:USERPROFILE) {
        $nvmRoot = Join-Path $env:USERPROFILE 'AppData\Roaming\nvm'
    }
    if ($nvmRoot -and (Test-Path $nvmRoot)) {
        try {
            $latest = Get-ChildItem -Path $nvmRoot -Directory -ErrorAction Stop |
                Sort-Object Name -Descending |
                Select-Object -First 1
            if ($latest) {
                $candidate = Join-Path $latest.FullName 'node.exe'
                if (Test-Path $candidate) {
                    $resolvedNvm = (Resolve-Path $candidate).ProviderPath
                    Write-Host "Found node via NVM install: $resolvedNvm" -ForegroundColor DarkGray
                    return $resolvedNvm
                }
            }
        } catch {
            Write-Host "Unable to enumerate NVM installs: $($_.Exception.Message)" -ForegroundColor DarkGray
        }
    }

    throw 'Unable to locate node executable. Install Node.js (LTS) and ensure node.exe is on PATH or supply -NodeExecutable.'
}

Stop-ServiceIfExists -Name $FrontendServiceName
Stop-ServiceIfExists -Name $BackendServiceName

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
             $iisAccessible = $false
             $importedWebModule = $false
         }
{{ ... }}
     }
 }

{{ ... }}
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
    $pythonExe = Resolve-PythonExecutable -PreferredPath $PythonExecutable
    $nodeExe = Resolve-NodeExecutable -PreferredPath $NodeExecutable
    $npmExe = $null
    $npmCommand = Get-Command npm -ErrorAction SilentlyContinue
    if ($npmCommand -and $npmCommand.Source) {
        $candidateNpm = (Resolve-Path $npmCommand.Source).ProviderPath
        if ($candidateNpm.ToLower().EndsWith('npm.ps1')) {
            $cmdFallback = Join-Path (Split-Path $candidateNpm) 'npm.cmd'
            if (Test-Path $cmdFallback) {
                $npmExe = (Resolve-Path $cmdFallback).ProviderPath
                Write-Host "npm command shim is PowerShell script; switching to npm.cmd at $npmExe" -ForegroundColor DarkGray
            }
        } else {
            $npmExe = $candidateNpm
            Write-Host "npm resolved to $npmExe" -ForegroundColor DarkGray
        }
    }

    if (-not $npmExe) {
        $npmFallback = Join-Path (Split-Path $nodeExe) 'npm.cmd'
        if (Test-Path $npmFallback) {
            $npmExe = (Resolve-Path $npmFallback).ProviderPath
            Write-Host "npm resolved via node directory: $npmExe" -ForegroundColor DarkGray
        } else {
            $npxFallback = Join-Path (Split-Path $nodeExe) 'npm.ps1'
            if (Test-Path $npxFallback) {
                $npmExe = (Resolve-Path $npxFallback).ProviderPath
                Write-Warning "Falling back to npm.ps1 shim at $npmExe; prefer npm.cmd for compatibility."
            } else {
                throw 'Unable to locate npm command. Ensure npm is installed with Node.js or add it to PATH.'
            }
        }
    }

    $nodeDir = Split-Path $nodeExe -Parent
    if ($nodeDir -and (Test-Path $nodeDir)) {
        Write-Host "Ensuring Node directory on PATH for child processes: $nodeDir" -ForegroundColor DarkGray
        $env:Path = "$nodeDir;${env:Path}"
    }

    Write-Host "Python resolved to $pythonExe" -ForegroundColor DarkGray
    Write-Host "Node resolved to $nodeExe" -ForegroundColor DarkGray

    $venvPath = Join-Path $TargetRoot '.venv'
    if (Test-Path $venvPath) {
{{ ... }}
        Remove-Item -Path $venvPath -Recurse -Force
    }
    Write-Host "Creating Python virtual environment" -ForegroundColor Cyan
    & $pythonExe -m venv $venvPath
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
            & $npmExe 'ci' '--omit=dev'
            Write-Host "Building Next.js frontend" -ForegroundColor Cyan
            & $npmExe 'run' 'build'
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
