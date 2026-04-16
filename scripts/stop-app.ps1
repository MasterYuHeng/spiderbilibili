$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$runtimeDir = Join-Path $root ".runtime"
$processStateFile = Join-Path $runtimeDir "app-processes.json"
$localAppComposeFile = Join-Path $root "docker-compose.local-app.yml"
$localAppEnvFile = Join-Path $root "docker\.env.local-app"

function Write-AppStep {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Message
  )

  Write-Host "[app] $Message" -ForegroundColor Yellow
}

function Get-RecordedProcessState {
  if (-not (Test-Path $processStateFile)) {
    return @()
  }

  try {
    $state = Get-Content -Path $processStateFile -Raw | ConvertFrom-Json
  }
  catch {
    Remove-Item -Path $processStateFile -Force -ErrorAction SilentlyContinue
    return @()
  }

  if ($null -eq $state.processes) {
    return @()
  }

  return @($state.processes)
}

function Get-ProcessTreeIds {
  param(
    [Parameter(Mandatory = $true)]
    [int]$RootProcessId
  )

  $queue = [System.Collections.Generic.Queue[int]]::new()
  $visited = [System.Collections.Generic.HashSet[int]]::new()
  $allProcesses = @(Get-CimInstance Win32_Process)

  $queue.Enqueue($RootProcessId)

  while ($queue.Count -gt 0) {
    $currentId = $queue.Dequeue()
    if (-not $visited.Add($currentId)) {
      continue
    }

    foreach ($child in $allProcesses) {
      if ($child.ParentProcessId -eq $currentId) {
        $queue.Enqueue([int]$child.ProcessId)
      }
    }
  }

  return @($visited)
}

function Stop-RecordedProcesses {
  foreach ($record in (Get-RecordedProcessState)) {
    $process = Get-Process -Id $record.id -ErrorAction SilentlyContinue
    if ($null -eq $process) {
      continue
    }

    $currentStartTimeUtc = $null
    try {
      $currentStartTimeUtc = $process.StartTime.ToUniversalTime().ToString("o")
    }
    catch {
      continue
    }

    if ($currentStartTimeUtc -ne $record.startTimeUtc) {
      continue
    }

    $processIdsToStop = Get-ProcessTreeIds -RootProcessId $process.Id | Sort-Object -Descending
    foreach ($processId in $processIdsToStop) {
      Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }

    Write-AppStep "Stopped $($record.role) process tree"
  }

  Remove-Item -Path $processStateFile -Force -ErrorAction SilentlyContinue
}

Stop-RecordedProcesses

Write-AppStep "Stopping local app web container"
$composeArguments = @()
if (Test-Path $localAppEnvFile) {
  $composeArguments += @("--env-file", $localAppEnvFile)
}
$composeArguments += @("-f", $localAppComposeFile, "down")
docker compose @composeArguments

Write-AppStep "Stopping PostgreSQL and Redis containers"
Set-Location $root
docker compose down

Write-Host ""
Write-Host "Local app environment stopped." -ForegroundColor Green
