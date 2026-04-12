param(
  [switch]$NoMonitor,
  [switch]$SkipOpenBrowser
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot "common.ps1")

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$python = Join-Path $root ".venv\Scripts\python.exe"
$celery = Join-Path $root ".venv\Scripts\celery.exe"
$backendStartScript = Join-Path $PSScriptRoot "start-backend.ps1"
$workerStartScript = Join-Path $PSScriptRoot "start-worker.ps1"
$frontendStartScript = Join-Path $PSScriptRoot "start-frontend.ps1"
$backendEnv = Join-Path $backend ".env"
$backendEnvExample = Join-Path $backend ".env.example"
$frontendNodeModules = Join-Path $frontend "node_modules"
$runtimeDir = Join-Path $root ".runtime"
$logDir = Join-Path $runtimeDir "logs"
$devProcessStateFile = Join-Path $runtimeDir "dev-processes.json"
$playwrightBrowserRoot = if ($env:PLAYWRIGHT_BROWSERS_PATH) {
  $env:PLAYWRIGHT_BROWSERS_PATH
}
else {
  Join-Path $env:LOCALAPPDATA "ms-playwright"
}
$launchSessionId = Get-Date -Format "yyyyMMdd-HHmmss"
$frontendUrl = "http://127.0.0.1:5174"
$backendUrl = "http://127.0.0.1:8014"

function Write-LauncherStep {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Message
  )

  Write-Host "[launcher] $Message" -ForegroundColor Cyan
}

function Ensure-RuntimeDirectory {
  foreach ($path in @($runtimeDir, $logDir)) {
    if (-not (Test-Path $path)) {
      New-Item -ItemType Directory -Path $path | Out-Null
    }
  }
}

function Resolve-HostPythonCommand {
  if (Get-Command py -ErrorAction SilentlyContinue) {
    return @{
      Command = "py"
      Arguments = @("-3.11")
    }
  }

  if (Get-Command python -ErrorAction SilentlyContinue) {
    return @{
      Command = "python"
      Arguments = @()
    }
  }

  throw "Python 3.11 was not found. Please install Python 3.11 and retry."
}

function Ensure-BackendEnvFile {
  if (Test-Path $backendEnv) {
    return
  }

  if (-not (Test-Path $backendEnvExample)) {
    throw "Backend environment template was not found: $backendEnvExample"
  }

  Write-LauncherStep "backend\\.env not found, creating it from .env.example"
  Copy-Item -Path $backendEnvExample -Destination $backendEnv
}

function Ensure-BackendRuntime {
  if ((Test-Path $python) -and (Test-Path $celery)) {
    return
  }

  $hostPython = Resolve-HostPythonCommand
  $hostPythonCommand = $hostPython.Command
  $hostPythonArgs = @($hostPython.Arguments)

  if (-not (Test-Path $python)) {
    Write-LauncherStep "Creating local virtual environment in .venv"
    & $hostPythonCommand @hostPythonArgs -m venv (Join-Path $root ".venv")
  }

  if (-not (Test-Path $python)) {
    throw "Backend Python interpreter was not found after creating the virtual environment: $python"
  }

  Write-LauncherStep "Installing backend dependencies"
  & $python -m pip install --upgrade pip
  & $python -m pip install -r (Join-Path $backend "requirements.txt")

  if (-not (Test-Path $celery)) {
    throw "Celery executable was not found after installing backend dependencies: $celery"
  }
}

function Test-PlaywrightChromiumInstalled {
  if (-not (Test-Path $playwrightBrowserRoot)) {
    return $false
  }

  $chromiumDirectories = @(
    Get-ChildItem -Path $playwrightBrowserRoot -Directory -Filter "chromium-*" -ErrorAction SilentlyContinue
  )
  return $chromiumDirectories.Count -gt 0
}

function Ensure-PlaywrightRuntime {
  if (-not (Test-Path $python)) {
    throw "Backend Python interpreter was not found before installing Playwright: $python"
  }

  if (Test-PlaywrightChromiumInstalled) {
    return
  }

  Write-LauncherStep "Installing Playwright Chromium runtime for the crawler"
  & $python -m playwright install chromium
}

function Ensure-FrontendDependencies {
  if (Test-Path $frontendNodeModules) {
    return
  }

  Write-LauncherStep "Installing frontend dependencies"
  Push-Location $frontend
  try {
    npm install
  }
  finally {
    Pop-Location
  }
}

function Get-NpmCommandPath {
  foreach ($candidate in @("npm.cmd", "npm.exe", "npm")) {
    $npmCommand = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($null -ne $npmCommand) {
      return $npmCommand.Source
    }
  }

  throw "npm is not installed or not available in PATH."
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

function Get-ListeningProcessRecords {
  param(
    [Parameter(Mandatory = $true)]
    [int[]]$Ports
  )

  $records = @()
  foreach ($port in $Ports) {
    $connections = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
    foreach ($connection in $connections) {
      $process = Get-CimInstance Win32_Process -Filter ("ProcessId = " + $connection.OwningProcess) -ErrorAction SilentlyContinue
      if ($null -eq $process) {
        continue
      }

      $records += [pscustomobject]@{
        Port = $port
        ProcessId = [int]$process.ProcessId
        Name = $process.Name
        ExecutablePath = [string]$process.ExecutablePath
        CommandLine = [string]$process.CommandLine
      }
    }
  }

  return @($records | Sort-Object ProcessId -Unique)
}

function Test-IsProjectDevProcess {
  param(
    [Parameter(Mandatory = $true)]
    [pscustomobject]$ProcessRecord
  )

  $hints = @(
    [string]$root,
    [string]$backend,
    [string]$frontend,
    "app.main:app",
    "uvicorn",
    "vite",
    "npm run dev"
  ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }

  $haystacks = @(
    [string]$ProcessRecord.ExecutablePath,
    [string]$ProcessRecord.CommandLine
  )

  foreach ($haystack in $haystacks) {
    if ([string]::IsNullOrWhiteSpace($haystack)) {
      continue
    }

    foreach ($hint in $hints) {
      if ($haystack.IndexOf($hint, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
        return $true
      }
    }
  }

  return $false
}

function Stop-LingeringDevProcesses {
  $lingeringRecords = @(Get-ListeningProcessRecords -Ports @(8014, 5174) | Where-Object { Test-IsProjectDevProcess -ProcessRecord $_ })
  if ($lingeringRecords.Count -eq 0) {
    return
  }

  Write-LauncherStep "Stopping lingering project processes from a previous run"
  foreach ($record in $lingeringRecords) {
    Stop-Process -Id $record.ProcessId -Force -ErrorAction SilentlyContinue
  }

  Start-Sleep -Seconds 2
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
    [string]$StdErrPath,
    [string]$ProbeUrl = ""
  )

  Initialize-LogFile -Path $StdOutPath
  Initialize-LogFile -Path $StdErrPath

  $process = Start-Process `
    -FilePath $FilePath `
    -ArgumentList $ArgumentList `
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
    ProbeUrl = $ProbeUrl
  }
}

function Save-DevProcessState {
  param(
    [Parameter(Mandatory = $true)]
    [array]$Processes
  )

  Ensure-RuntimeDirectory

  $state = [pscustomobject]@{
    updatedAt = (Get-Date).ToUniversalTime().ToString("o")
    processes = @(
      foreach ($processInfo in $Processes) {
        [pscustomobject]@{
          role = $processInfo.Role
          id = $processInfo.Process.Id
          startTimeUtc = $processInfo.Process.StartTime.ToUniversalTime().ToString("o")
          stdoutPath = $processInfo.StdOutPath
          stderrPath = $processInfo.StdErrPath
        }
      }
    )
  }

  $state | ConvertTo-Json -Depth 4 | Set-Content -Path $devProcessStateFile -Encoding UTF8
}

function Test-HttpReady {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Url
  )

  try {
    $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
    return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
  }
  catch {
    return $false
  }
}

function Wait-HttpReady {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Url,
    [int]$TimeoutSeconds = 90
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)

  while ((Get-Date) -lt $deadline) {
    if (Test-HttpReady -Url $Url) {
      return $true
    }

    Start-Sleep -Seconds 2
  }

  return $false
}

function Get-BackendHealthSnapshot {
  param(
    [string]$Url = "$backendUrl/api/health"
  )

  try {
    return Invoke-RestMethod -Uri $Url -UseBasicParsing -TimeoutSec 5
  }
  catch {
    return $null
  }
}

function Wait-BackendRuntimeReady {
  param(
    [int]$TimeoutSeconds = 90
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    $payload = Get-BackendHealthSnapshot
    if ($null -eq $payload) {
      Start-Sleep -Seconds 2
      continue
    }

    $data = $payload.data
    if (
      $null -ne $data -and
      $data.status -eq "ok" -and
      $data.components.database -eq "ok" -and
      $data.components.redis -eq "ok" -and
      $data.components.worker -eq "ok" -and
      [int]$data.indicators.active_workers -ge 1
    ) {
      return $true
    }

    Start-Sleep -Seconds 2
  }

  return $false
}

function Get-ContainerDisplayStatus {
  param(
    [Parameter(Mandatory = $true)]
    [string]$ContainerName
  )

  $status = Get-ContainerRuntimeStatus -ContainerName $ContainerName
  if ([string]::IsNullOrWhiteSpace($status)) {
    return "missing"
  }

  return $status
}

function Get-ProcessDisplayStatus {
  param(
    [Parameter(Mandatory = $true)]
    [pscustomobject]$ProcessInfo
  )

  $process = Get-Process -Id $ProcessInfo.Process.Id -ErrorAction SilentlyContinue
  if ($null -eq $process) {
    return "stopped"
  }

  if ([string]::IsNullOrWhiteSpace($ProcessInfo.ProbeUrl)) {
    return "running"
  }

  if (Test-HttpReady -Url $ProcessInfo.ProbeUrl) {
    return "ready"
  }

  return "starting"
}

function Get-RecentLogLines {
  param(
    [Parameter(Mandatory = $true)]
    [string]$StdOutPath,
    [Parameter(Mandatory = $true)]
    [string]$StdErrPath,
    [int]$MaxLines = 2
  )

  $items = @()

  if (Test-Path $StdErrPath) {
    $items += Get-Content -Path $StdErrPath -Tail $MaxLines -ErrorAction SilentlyContinue |
      Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
      ForEach-Object { "ERR> $_" }
  }

  if ($items.Count -lt $MaxLines -and (Test-Path $StdOutPath)) {
    $remaining = $MaxLines - $items.Count
    $items += Get-Content -Path $StdOutPath -Tail $remaining -ErrorAction SilentlyContinue |
      Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
      ForEach-Object { "OUT> $_" }
  }

  return @($items | Select-Object -Last $MaxLines)
}

function Write-MonitorLine {
  param(
    [string]$Name,
    [string]$Status,
    [string]$ProcessIdText = "",
    [string]$Hint = ""
  )

  $statusColor = switch ($Status) {
    "ready" { "Green" }
    "running" { "Green" }
    "healthy" { "Green" }
    "starting" { "Yellow" }
    "created" { "Yellow" }
    "missing" { "DarkYellow" }
    "stopped" { "Red" }
    default { "Gray" }
  }

  $nameText = $Name.PadRight(12)
  $pidText = if ($ProcessIdText) { $ProcessIdText.PadRight(8) } else { "-".PadRight(8) }

  Write-Host $nameText -NoNewline -ForegroundColor Cyan
  Write-Host $Status.PadRight(10) -NoNewline -ForegroundColor $statusColor
  Write-Host $pidText -NoNewline -ForegroundColor Gray
  Write-Host $Hint -ForegroundColor White
}

function Show-DevMonitor {
  param(
    [Parameter(Mandatory = $true)]
    [array]$Processes
  )

  while ($true) {
    Clear-Host
    Write-Host "SpiderBilibili Development Monitor" -ForegroundColor Cyan
    Write-Host ("Updated: " + (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")) -ForegroundColor DarkGray
    Write-Host "Press Q to close this monitor window. Services will keep running in the background." -ForegroundColor DarkGray
    Write-Host "Use close-dev.bat when you want to stop everything." -ForegroundColor DarkGray
    Write-Host ""

    Write-Host "Infra" -ForegroundColor White
    Write-Host "Name        Status    PID     Hint" -ForegroundColor DarkGray
    Write-MonitorLine -Name "postgres" -Status (Get-ContainerDisplayStatus -ContainerName "spiderbilibili-postgres") -Hint "docker compose"
    Write-MonitorLine -Name "redis" -Status (Get-ContainerDisplayStatus -ContainerName "spiderbilibili-redis") -Hint "docker compose"

    Write-Host ""
    Write-Host "Services" -ForegroundColor White
    Write-Host "Name        Status    PID     Hint" -ForegroundColor DarkGray

    foreach ($processInfo in $Processes) {
      $hint = switch ($processInfo.Role) {
        "backend" { $backendUrl }
        "frontend" { $frontendUrl }
        default { "background process" }
      }

      Write-MonitorLine `
        -Name $processInfo.Role `
        -Status (Get-ProcessDisplayStatus -ProcessInfo $processInfo) `
        -ProcessIdText ([string]$processInfo.Process.Id) `
        -Hint $hint
    }

    Write-Host ""
    Write-Host "Recent Logs" -ForegroundColor White
    foreach ($processInfo in $Processes) {
      Write-Host ("[" + $processInfo.Role + "]") -ForegroundColor Cyan
      $recentLines = Get-RecentLogLines -StdOutPath $processInfo.StdOutPath -StdErrPath $processInfo.StdErrPath
      if (-not $recentLines.Count) {
        Write-Host "  no recent output" -ForegroundColor DarkGray
      }
      else {
        foreach ($line in $recentLines) {
          Write-Host ("  " + $line) -ForegroundColor Gray
        }
      }
    }

    Start-Sleep -Milliseconds 800
    while ([Console]::KeyAvailable) {
      $key = [Console]::ReadKey($true)
      if ($key.Key -eq [ConsoleKey]::Q) {
        return
      }
    }
  }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw "Docker is not installed or not available in PATH."
}

Ensure-BackendEnvFile
Ensure-BackendRuntime
Ensure-PlaywrightRuntime
Ensure-FrontendDependencies
Ensure-RuntimeDirectory
Stop-LingeringDevProcesses

Set-Location $root
Write-LauncherStep "Starting PostgreSQL and Redis containers"
docker compose up -d
Wait-ContainerHealthy -ContainerName "spiderbilibili-postgres"
Wait-ContainerHealthy -ContainerName "spiderbilibili-redis"

Write-LauncherStep "Starting backend, worker, and frontend as hidden background services"
$backendProcess = Start-BackgroundProcess `
  -Role "backend" `
  -FilePath "powershell.exe" `
  -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $backendStartScript, "-DisableReload") `
  -WorkingDirectory $root `
  -StdOutPath (New-LogFilePath -Role "backend" -Stream "out") `
  -StdErrPath (New-LogFilePath -Role "backend" -Stream "err") `
  -ProbeUrl $backendUrl

$workerProcess = Start-BackgroundProcess `
  -Role "worker" `
  -FilePath "powershell.exe" `
  -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $workerStartScript) `
  -WorkingDirectory $root `
  -StdOutPath (New-LogFilePath -Role "worker" -Stream "out") `
  -StdErrPath (New-LogFilePath -Role "worker" -Stream "err")

$frontendProcess = Start-BackgroundProcess `
  -Role "frontend" `
  -FilePath "powershell.exe" `
  -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $frontendStartScript) `
  -WorkingDirectory $root `
  -StdOutPath (New-LogFilePath -Role "frontend" -Stream "out") `
  -StdErrPath (New-LogFilePath -Role "frontend" -Stream "err") `
  -ProbeUrl $frontendUrl

$processes = @($backendProcess, $workerProcess, $frontendProcess)
Save-DevProcessState -Processes $processes

Write-LauncherStep "Waiting for backend, worker, and frontend to become available"
$backendReady = Wait-BackendRuntimeReady
$frontendReady = Wait-HttpReady -Url $frontendUrl

if ($backendReady -and $frontendReady) {
  if ($SkipOpenBrowser) {
    Write-LauncherStep "Frontend, backend, and worker are ready"
  }
  else {
    Write-LauncherStep "Opening the frontend page in your default browser"
    Start-Process $frontendUrl | Out-Null
  }
}
else {
  if (-not $backendReady) {
    Write-Warning "The backend runtime did not report a ready worker within the expected time. Check the backend and worker logs."
  }
  if (-not $frontendReady) {
    Write-Warning "The frontend page did not respond within the expected time. You can still open $frontendUrl manually."
  }
}

if (-not $NoMonitor) {
  Show-DevMonitor -Processes $processes
}
