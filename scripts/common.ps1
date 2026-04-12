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
