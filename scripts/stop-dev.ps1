param(
  [switch]$CloseMonitor
)

$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$runtimeDir = Join-Path $root ".runtime"
$devProcessStateFile = Join-Path $root ".runtime\dev-processes.json"
$monitorCloseFlagFile = Join-Path $runtimeDir "dev-monitor.close.flag"

function Write-StopStep {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Message
  )

  Write-Host "[closer] $Message" -ForegroundColor Yellow
}

function Get-RecordedProcessState {
  if (-not (Test-Path $devProcessStateFile)) {
    return @()
  }

  try {
    $state = Get-Content -Path $devProcessStateFile -Raw | ConvertFrom-Json
  }
  catch {
    Write-Warning "The launcher process record is unreadable and will be removed."
    Remove-Item -Path $devProcessStateFile -Force -ErrorAction SilentlyContinue
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
  $records = Get-RecordedProcessState

  if ($records.Count -eq 0) {
    Write-StopStep "No recorded launcher processes were found"
    return
  }

  foreach ($record in $records) {
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
      $targetProcess = Get-Process -Id $processId -ErrorAction SilentlyContinue
      if ($null -eq $targetProcess) {
        continue
      }

      Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }

    Write-StopStep "Stopped $($record.role) process tree"
  }

  Remove-Item -Path $devProcessStateFile -Force -ErrorAction SilentlyContinue
}

function Get-LingeringWorkspaceProcessRecords {
  $records = @()
  $listeningProcessIds = @(
    Get-NetTCPConnection -LocalPort 8014,5174 -State Listen -ErrorAction SilentlyContinue |
      Select-Object -ExpandProperty OwningProcess
  )
  $allProcesses = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
  foreach ($process in $allProcesses) {
    $commandLine = [string]$process.CommandLine
    if ([string]::IsNullOrWhiteSpace($commandLine)) {
      continue
    }

    $matchesWorkspace = $commandLine.IndexOf([string]$root, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
    $matchesWorker = $commandLine.IndexOf("app.worker.celery_app", [System.StringComparison]::OrdinalIgnoreCase) -ge 0
    $matchesKnownPort = $listeningProcessIds -contains [int]$process.ProcessId
    if (-not ($matchesWorkspace -or $matchesWorker -or $matchesKnownPort)) {
      continue
    }

    $records += [pscustomobject]@{
      ProcessId = [int]$process.ProcessId
      Name = [string]$process.Name
      CommandLine = $commandLine
    }
  }

  return @($records | Where-Object { $_.ProcessId -ne $PID } | Sort-Object ProcessId -Unique)
}

function Stop-LingeringWorkspaceProcesses {
  $records = Get-LingeringWorkspaceProcessRecords
  if ($records.Count -eq 0) {
    return
  }

  foreach ($record in $records) {
    Stop-Process -Id $record.ProcessId -Force -ErrorAction SilentlyContinue
    Write-StopStep "Stopped lingering $($record.Name) process ($($record.ProcessId))"
  }
}

Stop-RecordedProcesses
Stop-LingeringWorkspaceProcesses

Write-StopStep "Stopping PostgreSQL and Redis containers"
Set-Location $root
docker compose down

if ($CloseMonitor) {
  if (-not (Test-Path $runtimeDir)) {
    New-Item -ItemType Directory -Path $runtimeDir | Out-Null
  }
  Set-Content -Path $monitorCloseFlagFile -Value ((Get-Date).ToString("o")) -Encoding UTF8
}

Write-Host ""
Write-Host "Development environment stopped." -ForegroundColor Green
