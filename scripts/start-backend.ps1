param(
  [switch]$DisableReload
)

$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$python = Join-Path $root ".venv\Scripts\python.exe"
$backend = Join-Path $root "backend"

if (-not (Test-Path $python)) {
  throw "Backend Python interpreter was not found: $python"
}

Set-Location $backend
$migrationArguments = @("-m", "alembic", "upgrade", "head")
& $python @migrationArguments

$arguments = @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8014")
if (-not $DisableReload) {
  $arguments += "--reload"
}

& $python @arguments
