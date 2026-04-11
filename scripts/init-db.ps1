$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot "common.ps1")
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$alembic = Join-Path $root ".venv\Scripts\alembic.exe"
$python = Join-Path $root ".venv\Scripts\python.exe"
$backend = Join-Path $root "backend"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw "Docker is not installed or not available in PATH."
}

if (-not (Test-Path $alembic)) {
  throw "Alembic executable was not found: $alembic"
}

if (-not (Test-Path $python)) {
  throw "Backend Python interpreter was not found: $python"
}

Set-Location $root
docker compose up -d
Wait-ContainerHealthy -ContainerName "spiderbilibili-postgres"

Set-Location $backend
& $alembic upgrade head
& $python -m app.db.bootstrap
