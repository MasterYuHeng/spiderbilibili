$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$celery = Join-Path $root ".venv\Scripts\celery.exe"
$backend = Join-Path $root "backend"

if (-not (Test-Path $celery)) {
  throw "Celery executable was not found: $celery"
}

Set-Location $backend
$pool = if ($env:CELERY_POOL) { $env:CELERY_POOL } else { "solo" }
$concurrency = if ($env:CELERY_CONCURRENCY) { $env:CELERY_CONCURRENCY } else { "1" }

& $celery -A app.worker.celery_app worker --loglevel=info --pool=$pool --concurrency=$concurrency
