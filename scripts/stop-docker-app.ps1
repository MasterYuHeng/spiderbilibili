$ErrorActionPreference = 'Stop'

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$composeFile = Join-Path $root "docker-compose.app.yml"
$envFile = Join-Path $root "docker\.env.app.local"

function Write-DockerStep {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Message
  )

  Write-Host "[docker-app] $Message" -ForegroundColor Yellow
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw "Docker is not installed or not available in PATH."
}

if (-not (Test-Path $envFile)) {
  Write-DockerStep "docker\\.env.app.local was not found, using compose defaults"
}

Set-Location $root
Write-DockerStep "Stopping app-only Docker stack"
$composeArguments = @()
if (Test-Path $envFile) {
  $composeArguments += @("--env-file", $envFile)
}
$composeArguments += @("-f", $composeFile, "down")

docker compose @composeArguments
if ($LASTEXITCODE -ne 0) {
  throw "Docker Compose failed to stop the app-only stack."
}

Write-Host ""
Write-Host "Docker app environment stopped." -ForegroundColor Green
