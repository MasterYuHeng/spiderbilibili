$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot "common.ps1")
$root = Resolve-Path (Join-Path $PSScriptRoot "..")

Set-Location $root

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw "Docker is not installed or not available in PATH."
}

docker compose up -d
Wait-ContainerHealthy -ContainerName "spiderbilibili-postgres"
Wait-ContainerHealthy -ContainerName "spiderbilibili-redis"
docker compose ps
