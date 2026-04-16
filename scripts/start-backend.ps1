param(
  [switch]$DisableReload,
  [string]$PythonPath = ""
)

$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$python = if ([string]::IsNullOrWhiteSpace($PythonPath)) {
  Join-Path $root ".venv\Scripts\python.exe"
}
else {
  $PythonPath
}
$backend = Join-Path $root "backend"
$migrationStatusScript = Join-Path $PSScriptRoot "backend_migration_status.py"

if (-not (Test-Path $python)) {
  throw "Backend Python interpreter was not found: $python"
}

function Get-BackendMigrationStatus {
  $output = & $python $migrationStatusScript 2>$null
  if ($LASTEXITCODE -ne 0) {
    return $null
  }

  $raw = ((@($output) -join "`n").Trim())
  if ([string]::IsNullOrWhiteSpace($raw)) {
    return $null
  }

  try {
    return ($raw | ConvertFrom-Json)
  }
  catch {
    return $null
  }
}

function Test-BackendSchemaUpToDate {
  $status = Get-BackendMigrationStatus
  if ($null -eq $status) {
    return $false
  }

  $currentRevisions = @($status.current)
  $headRevisions = @($status.heads)
  if ($headRevisions.Count -eq 0) {
    return $false
  }

  if ($currentRevisions.Count -ne $headRevisions.Count) {
    return $false
  }

  for ($index = 0; $index -lt $headRevisions.Count; $index += 1) {
    if ([string]$currentRevisions[$index] -ne [string]$headRevisions[$index]) {
      return $false
    }
  }

  return $true
}

Set-Location $backend
if (-not (Test-BackendSchemaUpToDate)) {
  Write-Host "[backend] Applying pending database migrations"
  $migrationArguments = @("-m", "alembic", "upgrade", "head")
  & $python @migrationArguments
}
else {
  Write-Host "[backend] Database schema is already up to date"
}

$arguments = @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8014")
if (-not $DisableReload) {
  $arguments += "--reload"
}

& $python @arguments
