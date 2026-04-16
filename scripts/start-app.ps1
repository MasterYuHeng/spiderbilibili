param(
  [switch]$SkipOpenBrowser
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot "common.ps1")

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$backend = Join-Path $root "backend"
$venvDir = Join-Path $root ".venv-app"
$python = Join-Path $venvDir "Scripts\python.exe"
$celery = Join-Path $venvDir "Scripts\celery.exe"
$backendStartScript = Join-Path $PSScriptRoot "start-backend.ps1"
$workerStartScript = Join-Path $PSScriptRoot "start-worker.ps1"
$backendEnv = Join-Path $backend ".env"
$backendEnvExample = Join-Path $backend ".env.example"
$runtimeDir = Join-Path $root ".runtime"
$logDir = Join-Path $runtimeDir "logs"
$processStateFile = Join-Path $runtimeDir "app-processes.json"
$localAppComposeFile = Join-Path $root "docker-compose.local-app.yml"
$localAppEnvFile = Join-Path $root "docker\.env.local-app"
$localAppEnvExample = Join-Path $root "docker\.env.local-app.example"
$launchSessionId = Get-Date -Format "yyyyMMdd-HHmmss"
$backendUrl = "http://127.0.0.1:8014"
$backendHealthUrl = "$backendUrl/api/health"

function Write-AppStep {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Message
  )

  Write-Host "[app] $Message" -ForegroundColor Cyan
}

function Ensure-RuntimeDirectory {
  foreach ($path in @($runtimeDir, $logDir)) {
    if (-not (Test-Path $path)) {
      New-Item -ItemType Directory -Path $path | Out-Null
    }
  }
}

function Ensure-BackendEnvFile {
  if (Test-Path $backendEnv) {
    return
  }

  if (-not (Test-Path $backendEnvExample)) {
    throw "Backend environment template was not found: $backendEnvExample"
  }

  Write-AppStep "backend\\.env not found, creating it from .env.example"
  Copy-Item -Path $backendEnvExample -Destination $backendEnv
}

function Ensure-LocalAppEnvFile {
  if (Test-Path $localAppEnvFile) {
    return
  }

  if (-not (Test-Path $localAppEnvExample)) {
    throw "Local app Docker environment template was not found: $localAppEnvExample"
  }

  Write-AppStep "Creating docker\\.env.local-app from template"
  Copy-Item -Path $localAppEnvExample -Destination $localAppEnvFile
}

function Get-EnvFileValue {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path,
    [Parameter(Mandatory = $true)]
    [string]$Name,
    [Parameter(Mandatory = $true)]
    [string]$Fallback
  )

  if (-not (Test-Path $Path)) {
    return $Fallback
  }

  $line = Get-Content -Path $Path |
    Where-Object { $_ -match ("^\s*" + [regex]::Escape($Name) + "=") } |
    Select-Object -First 1
  if ([string]::IsNullOrWhiteSpace($line)) {
    return $Fallback
  }

  $value = ($line -split "=", 2)[1].Trim()
  if ([string]::IsNullOrWhiteSpace($value)) {
    return $Fallback
  }

  return $value.Trim('"')
}

function Remove-InvalidVirtualEnvironment {
  if (-not (Test-Path $venvDir)) {
    return
  }

  Write-AppStep "Detected an invalid runtime virtual environment, rebuilding .venv-app"
  Remove-Item -LiteralPath $venvDir -Recurse -Force -ErrorAction Stop
}

function Ensure-BackendRuntime {
  if ((Test-Path $venvDir) -and (-not (Test-PythonExecutableHealthy -PythonPath $python))) {
    Remove-InvalidVirtualEnvironment
  }

  if (
    (Test-Path $python) -and
    (Test-Path $celery) -and
    (Test-PythonExecutableHealthy -PythonPath $python)
  ) {
    return
  }

  $hostPython = Resolve-HostPythonCommand
  if (-not (Test-Path $python)) {
    Write-AppStep "Creating local runtime virtual environment in .venv-app"
    & $hostPython.Command @($hostPython.Arguments) -m venv $venvDir
  }

  if (-not (Test-Path $python)) {
    throw "Backend Python interpreter was not found after creating the runtime environment: $python"
  }

  Write-AppStep "Installing lightweight backend runtime dependencies"
  & $python -m pip install --upgrade pip
  & $python -m pip install -r (Join-Path $backend "requirements.runtime.txt")

  if (-not (Test-Path $celery)) {
    throw "Celery executable was not found after installing runtime dependencies: $celery"
  }
}

function Initialize-LogFile {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path
  )

  Ensure-RuntimeDirectory
  $directory = Split-Path -Path $Path -Parent
  if (-not (Test-Path $directory)) {
    New-Item -ItemType Directory -Path $directory | Out-Null
  }

  if (Test-Path $Path) {
    Remove-Item -Path $Path -Force -ErrorAction SilentlyContinue
  }

  New-Item -ItemType File -Path $Path -Force | Out-Null
}

function New-LogFilePath {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Role,
    [Parameter(Mandatory = $true)]
    [ValidateSet("out", "err")]
    [string]$Stream
  )

  Ensure-RuntimeDirectory
  return (Join-Path $logDir ($launchSessionId + "-" + $Role + "." + $Stream + ".log"))
}

function Start-BackgroundProcess {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Role,
    [Parameter(Mandatory = $true)]
    [string]$FilePath,
    [Parameter(Mandatory = $true)]
    [string[]]$ArgumentList,
    [Parameter(Mandatory = $true)]
    [string]$WorkingDirectory,
    [Parameter(Mandatory = $true)]
    [string]$StdOutPath,
    [Parameter(Mandatory = $true)]
    [string]$StdErrPath
  )

  Initialize-LogFile -Path $StdOutPath
  Initialize-LogFile -Path $StdErrPath

  $process = Start-Process `
    -FilePath $FilePath `
    -ArgumentList (Join-ProcessArgumentList -ArgumentList $ArgumentList) `
    -WorkingDirectory $WorkingDirectory `
    -WindowStyle Hidden `
    -RedirectStandardOutput $StdOutPath `
    -RedirectStandardError $StdErrPath `
    -PassThru

  return [pscustomobject]@{
    Role = $Role
    Process = $process
    StdOutPath = $StdOutPath
    StdErrPath = $StdErrPath
  }
}

function Save-ProcessState {
  param(
    [Parameter(Mandatory = $true)]
    [array]$Processes
  )

  Ensure-RuntimeDirectory
  $state = [pscustomobject]@{
    updatedAt = (Get-Date).ToUniversalTime().ToString("o")
    processes = @(
      foreach ($item in $Processes) {
        [pscustomobject]@{
          role = $item.Role
          id = $item.Process.Id
          startTimeUtc = $item.Process.StartTime.ToUniversalTime().ToString("o")
        }
      }
    )
  }

  $state | ConvertTo-Json -Depth 4 | Set-Content -Path $processStateFile -Encoding UTF8
}

function Wait-HttpReady {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Url,
    [int]$TimeoutSeconds = 180
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
      if (Test-HttpReady -Url $Url -TimeoutSeconds 5) {
        return
      }

    Start-Sleep -Seconds 2
  }

  throw "URL '$Url' was not reachable within $TimeoutSeconds seconds."
}

function Test-PortAvailable {
  param(
    [Parameter(Mandatory = $true)]
    [int]$Port
  )

  $connections = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
  return $connections.Count -eq 0
}

function Resolve-WebPort {
  param(
    [Parameter(Mandatory = $true)]
    [int]$PreferredPort
  )

  $localWebStatus = Get-ContainerRuntimeStatus -ContainerName "spiderbilibili-local-web"
  if ($localWebStatus -in @("healthy", "running")) {
    return $PreferredPort
  }

  $resolvedPort = $PreferredPort
  while (-not (Test-PortAvailable -Port $resolvedPort)) {
    $resolvedPort += 1
  }

  return $resolvedPort
}

function Test-IsProjectRuntimeProcess {
  param(
    [Parameter(Mandatory = $true)]
    [pscustomobject]$ProcessRecord
  )

  return Test-ProcessMatchesHints -ProcessRecord $ProcessRecord -Hints @(
    [string]$root,
    [string]$backend,
    "app.main:app",
    "uvicorn",
    "celery",
    "app.worker.celery_app"
  )
}

function Stop-LingeringRuntimeProcesses {
  $records = @(
    Get-ListeningProcessRecords -Ports @(8014) |
      Where-Object { Test-IsProjectRuntimeProcess -ProcessRecord $_ }
  )

  foreach ($record in $records) {
    Stop-Process -Id $record.ProcessId -Force -ErrorAction SilentlyContinue
  }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw "Docker is not installed or not available in PATH."
}

Ensure-BackendEnvFile
Ensure-LocalAppEnvFile
Ensure-BackendRuntime
Ensure-RuntimeDirectory
Stop-LingeringRuntimeProcesses

$webPort = [int](Get-EnvFileValue -Path $localAppEnvFile -Name "WEB_PORT" -Fallback "8080")
$webPort = Resolve-WebPort -PreferredPort $webPort
$env:WEB_PORT = [string]$webPort
$appUrl = "http://127.0.0.1:$webPort"

Set-Location $root
Write-AppStep "Starting PostgreSQL and Redis containers"
docker compose up -d
Wait-ContainerHealthy -ContainerName "spiderbilibili-postgres"
Wait-ContainerHealthy -ContainerName "spiderbilibili-redis"

Write-AppStep "Starting local app web container"
docker compose --env-file $localAppEnvFile -f $localAppComposeFile down | Out-Null
docker compose --env-file $localAppEnvFile -f $localAppComposeFile up -d --build
Wait-ContainerHealthy -ContainerName "spiderbilibili-local-web" -TimeoutSeconds 240

Set-Item -Path "Env:APP_ENV" -Value "production"
Set-Item -Path "Env:APP_DEBUG" -Value "false"
Set-Item -Path "Env:APP_PORT" -Value "8014"
Set-Item -Path "Env:APP_CORS_ORIGINS" -Value "http://127.0.0.1:$webPort,http://localhost:$webPort"
Set-Item -Path "Env:APP_PUBLIC_BASE_URL" -Value $appUrl

Write-AppStep "Starting backend and worker as hidden background services"
$backendProcess = Start-BackgroundProcess `
  -Role "backend" `
  -FilePath "powershell.exe" `
  -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $backendStartScript, "-DisableReload", "-PythonPath", $python) `
  -WorkingDirectory $root `
  -StdOutPath (New-LogFilePath -Role "app-backend" -Stream "out") `
  -StdErrPath (New-LogFilePath -Role "app-backend" -Stream "err")

$workerProcess = Start-BackgroundProcess `
  -Role "worker" `
  -FilePath "powershell.exe" `
  -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $workerStartScript, "-CeleryPath", $celery) `
  -WorkingDirectory $root `
  -StdOutPath (New-LogFilePath -Role "app-worker" -Stream "out") `
  -StdErrPath (New-LogFilePath -Role "app-worker" -Stream "err")

$processes = @($backendProcess, $workerProcess)
Save-ProcessState -Processes $processes

Write-AppStep "Waiting for backend API and local app page to become available"
Wait-HttpReady -Url $backendHealthUrl -TimeoutSeconds 240
Wait-HttpReady -Url $appUrl -TimeoutSeconds 240

if ($SkipOpenBrowser) {
  Write-AppStep "SpiderBilibili local app is ready at $appUrl"
}
else {
  Write-AppStep "Opening the local app in your default browser"
  Start-Process $appUrl | Out-Null
}
