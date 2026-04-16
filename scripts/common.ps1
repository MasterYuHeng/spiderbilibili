function Get-ContainerRuntimeStatus {
  param(
    [Parameter(Mandatory = $true)]
    [string]$ContainerName
  )

  $dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
  if ($null -eq $dockerCommand) {
    return $null
  }

  try {
    $nameOutput = & $dockerCommand.Source ps -a --filter "name=^/$ContainerName$" --format "{{.Names}}" 2>$null
    if ($LASTEXITCODE -ne 0) {
      return $null
    }

    $containerNames = @($nameOutput | ForEach-Object { [string]$_ } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if (-not ($containerNames -contains $ContainerName)) {
      return $null
    }

    $statusOutput = & $dockerCommand.Source ps -a --filter "name=^/$ContainerName$" --format "{{.Status}}" 2>$null
    if ($LASTEXITCODE -ne 0) {
      return $null
    }

    $statusText = [string](($statusOutput | Select-Object -First 1) | Out-String)
    $statusText = $statusText.Trim()
    if ([string]::IsNullOrWhiteSpace($statusText)) {
      return $null
    }

    if ($statusText.IndexOf("(healthy)", [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
      return "healthy"
    }
    if ($statusText.IndexOf("(unhealthy)", [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
      return "unhealthy"
    }
    if ($statusText.StartsWith("Up", [System.StringComparison]::OrdinalIgnoreCase)) {
      return "running"
    }
    if ($statusText.StartsWith("Exited", [System.StringComparison]::OrdinalIgnoreCase)) {
      return "exited"
    }
    if ($statusText.StartsWith("Created", [System.StringComparison]::OrdinalIgnoreCase)) {
      return "created"
    }
    if ($statusText.StartsWith("Paused", [System.StringComparison]::OrdinalIgnoreCase)) {
      return "paused"
    }

    return $statusText
  }
  catch {
    return $null
  }
}

function Convert-ToProcessArgumentText {
  param(
    [AllowEmptyString()]
    [string]$Argument
  )

  $value = [string]$Argument
  if ($value.Length -eq 0) {
    return '""'
  }

  if ($value.IndexOfAny([char[]]@(' ', "`t", '"')) -lt 0) {
    return $value
  }

  $escaped = $value -replace '(\\*)"', '$1$1\"'
  $escaped = $escaped -replace '(\\+)$', '$1$1'
  return '"' + $escaped + '"'
}

function Join-ProcessArgumentList {
  param(
    [Parameter(Mandatory = $true)]
    [string[]]$ArgumentList
  )

  return (($ArgumentList | ForEach-Object { Convert-ToProcessArgumentText -Argument $_ }) -join ' ')
}

function Resolve-HostPythonCommand {
  if (Get-Command py -ErrorAction SilentlyContinue) {
    foreach ($candidate in @("-3.11", "-3.12", "-3")) {
      try {
        & py $candidate -c "import sys" 2>$null
        if ($LASTEXITCODE -eq 0) {
          return @{
            Command = "py"
            Arguments = @($candidate)
          }
        }
      }
      catch {
      }
    }
  }

  if (Get-Command python -ErrorAction SilentlyContinue) {
    try {
      & python -c "import sys" 2>$null
      if ($LASTEXITCODE -eq 0) {
        return @{
          Command = "python"
          Arguments = @()
        }
      }
    }
    catch {
    }
  }

  throw "A usable Python runtime was not found. Please install Python and retry."
}

function Test-PythonExecutableHealthy {
  param(
    [Parameter(Mandatory = $true)]
    [string]$PythonPath
  )

  if (-not (Test-Path $PythonPath)) {
    return $false
  }

  try {
    & $PythonPath -c "import sys" 2>$null
    return $LASTEXITCODE -eq 0
  }
  catch {
    return $false
  }
}

function Test-HttpReady {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Url,
    [int]$TimeoutSeconds = 5
  )

  try {
    $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSeconds
    return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
  }
  catch {
    return $false
  }
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
        Name = [string]$process.Name
        ExecutablePath = [string]$process.ExecutablePath
        CommandLine = [string]$process.CommandLine
      }
    }
  }

  return @($records | Sort-Object ProcessId -Unique)
}

function Test-ProcessMatchesHints {
  param(
    [Parameter(Mandatory = $true)]
    [pscustomobject]$ProcessRecord,
    [Parameter(Mandatory = $true)]
    [string[]]$Hints
  )

  $resolvedHints = @($Hints | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
  if ($resolvedHints.Count -eq 0) {
    return $false
  }

  $haystacks = @(
    [string]$ProcessRecord.ExecutablePath,
    [string]$ProcessRecord.CommandLine
  )

  foreach ($haystack in $haystacks) {
    if ([string]::IsNullOrWhiteSpace($haystack)) {
      continue
    }

    foreach ($hint in $resolvedHints) {
      if ($haystack.IndexOf($hint, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
        return $true
      }
    }
  }

  return $false
}

function Wait-ContainerHealthy {
  param(
    [Parameter(Mandatory = $true)]
    [string]$ContainerName,
    [int]$TimeoutSeconds = 60
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)

  while ((Get-Date) -lt $deadline) {
    $status = Get-ContainerRuntimeStatus -ContainerName $ContainerName
    if ($status -eq "healthy" -or $status -eq "running") {
      return
    }

    Start-Sleep -Seconds 2
  }

  throw "Container '$ContainerName' was not healthy within $TimeoutSeconds seconds."
}
