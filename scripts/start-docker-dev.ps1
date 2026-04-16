param(
  [switch]$SkipOpenBrowser
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot "common.ps1")

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$composeFile = Join-Path $root "docker-compose.dev-full.yml"
$envFile = Join-Path $root "docker\.env.dev-full"
$envExample = Join-Path $root "docker\.env.dev-full.example"

function Write-DockerStep {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Message
  )

  Write-Host "[docker-dev] $Message" -ForegroundColor Cyan
}

function Ensure-EnvFile {
  if (Test-Path $envFile) {
    return
  }

  Write-DockerStep "Creating docker\\.env.dev-full from template"
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

function Wait-HttpReady {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Url,
    [int]$TimeoutSeconds = 240
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    try {
      $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
      if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
        return
      }
    }
    catch {
    }

    Start-Sleep -Seconds 2
  }

  throw "URL '$Url' was not reachable within $TimeoutSeconds seconds."
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw "Docker is not installed or not available in PATH."
}

Ensure-EnvFile
$frontendPort = Get-EnvFileValue -Path $envFile -Name "FRONTEND_PORT" -Fallback "5174"
$backendPort = Get-EnvFileValue -Path $envFile -Name "BACKEND_PORT" -Fallback "8014"
$frontendUrl = "http://127.0.0.1:$frontendPort"
$backendHealthUrl = "http://127.0.0.1:$backendPort/api/health"

Set-Location $root
Write-DockerStep "Starting full Docker development stack"
docker compose --env-file $envFile -f $composeFile up -d --build
if ($LASTEXITCODE -ne 0) {
  throw "Docker Compose failed to start the full development stack."
}

Write-DockerStep "Waiting for backend and frontend"
Wait-ContainerHealthy -ContainerName "spiderbilibili-dev-postgres" -TimeoutSeconds 240
Wait-ContainerHealthy -ContainerName "spiderbilibili-dev-redis" -TimeoutSeconds 240
Wait-HttpReady -Url $backendHealthUrl -TimeoutSeconds 300
Wait-HttpReady -Url $frontendUrl -TimeoutSeconds 300

if ($SkipOpenBrowser) {
  Write-DockerStep "Docker development stack is ready at $frontendUrl"
}
else {
  Write-DockerStep "Opening the Docker development frontend"
  Start-Process $frontendUrl | Out-Null
}
