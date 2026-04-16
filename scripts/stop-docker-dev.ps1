$ErrorActionPreference = 'Stop'

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$composeFile = Join-Path $root "docker-compose.dev-full.yml"
$envFile = Join-Path $root "docker\.env.dev-full"

function Write-DockerStep {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Message
  )

  Write-Host "[docker-dev] $Message" -ForegroundColor Yellow
}

Set-Location $root
Write-DockerStep "Stopping full Docker development stack"
$composeArguments = @()
if (Test-Path $envFile) {
  $composeArguments += @("--env-file", $envFile)
}
$composeArguments += @("-f", $composeFile, "down")
docker compose @composeArguments
if ($LASTEXITCODE -ne 0) {
  throw "Docker Compose failed to stop the full development stack."
}

Write-Host ""
Write-Host "Docker development environment stopped." -ForegroundColor Green
