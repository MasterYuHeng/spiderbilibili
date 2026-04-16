param(
  [switch]$SkipOpenBrowser
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot "common.ps1")

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$composeFile = Join-Path $root "docker-compose.app.yml"
$envFile = Join-Path $root "docker\.env.app.local"
$envExample = Join-Path $root "docker\.env.app.local.example"

function Write-DockerStep {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Message
  )

  Write-Host "[docker-app] $Message" -ForegroundColor Cyan
}

function Ensure-DockerCommand {
  if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is not installed or not available in PATH."
  }
}

function Ensure-AppEnvFile {
  if (Test-Path $envFile) {
    return
  }

  if (-not (Test-Path $envExample)) {
    throw "Docker app environment template was not found: $envExample"
  }

  Write-DockerStep "Creating docker\\.env.app.local from template"
  Copy-Item -Path $envExample -Destination $envFile
}

function Get-EnvFileValue {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path,
    [Parameter(Mandatory = $true)]
    [string]$Name,
    [Parameter(Mandatory = $true)]
    [string]$Fallback
  )

  if (-not (Test-Path $Path)) {
    return $Fallback
  }

  $line = Get-Content -Path $Path |
    Where-Object { $_ -match ("^\s*" + [regex]::Escape($Name) + "=") } |
    Select-Object -First 1
  if ([string]::IsNullOrWhiteSpace($line)) {
    return $Fallback
  }

  $value = ($line -split "=", 2)[1].Trim()
  if ([string]::IsNullOrWhiteSpace($value)) {
    return $Fallback
  }

  return $value.Trim('"')
}

function Test-HttpReady {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Url
  )

  try {
    $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
    return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
  }
  catch {
    return $false
  }
}

function Wait-HttpReady {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Url,
    [int]$TimeoutSeconds = 180
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    if (Test-HttpReady -Url $Url) {
      return
    }

    Start-Sleep -Seconds 2
  }

  throw "URL '$Url' was not reachable within $TimeoutSeconds seconds."
}

Ensure-DockerCommand
Ensure-AppEnvFile

$webPort = Get-EnvFileValue -Path $envFile -Name "WEB_PORT" -Fallback "8080"
$appUrl = "http://127.0.0.1:$webPort"
$healthUrl = "$appUrl/api/health"

Set-Location $root
Write-DockerStep "Starting app-only Docker stack"
docker compose --env-file $envFile -f $composeFile up -d --build
if ($LASTEXITCODE -ne 0) {
  throw "Docker Compose failed to start the app-only stack."
}

Write-DockerStep "Waiting for backend and web services"
Wait-ContainerHealthy -ContainerName "spiderbilibili-app-backend" -TimeoutSeconds 240
Wait-HttpReady -Url $appUrl -TimeoutSeconds 240
Wait-HttpReady -Url $healthUrl -TimeoutSeconds 240

if ($SkipOpenBrowser) {
  Write-DockerStep "SpiderBilibili is ready at $appUrl"
}
else {
  Write-DockerStep "Opening SpiderBilibili in your default browser"
  Start-Process $appUrl | Out-Null
}
