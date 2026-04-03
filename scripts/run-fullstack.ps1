[CmdletBinding()]
param(
    [switch]$SkipBackendBuild,
    [switch]$StopBackendOnExit,
    [int]$FrontendPort = 5173,
    [int]$BackendPort = 8000
)

$ErrorActionPreference = "Stop"

function Assert-CommandAvailable {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found in PATH."
    }
}

function Invoke-Compose {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Args
    )

    & docker compose @Args

    if ($LASTEXITCODE -ne 0) {
        throw "docker compose $($Args -join ' ') failed with exit code $LASTEXITCODE."
    }
}

function Wait-ForHttp {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [int]$TimeoutSeconds = 120
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)

    while ((Get-Date) -lt $deadline) {
        try {
            return Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 4
        }
        catch {
            Start-Sleep -Seconds 2
        }
    }

    throw "Timed out waiting for '$Url'."
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$frontendDir = Join-Path $repoRoot "frontend"

if (-not (Test-Path $frontendDir)) {
    throw "Frontend directory not found at '$frontendDir'."
}

Assert-CommandAvailable -Name "docker"
Assert-CommandAvailable -Name "bun"

Write-Host "Repository: $repoRoot" -ForegroundColor Cyan
Set-Location $repoRoot

$composeArgs = @("up", "-d")
if (-not $SkipBackendBuild) {
    $composeArgs += "--build"
}

Write-Host "Starting backend with Docker Compose..." -ForegroundColor Cyan
Invoke-Compose -Args $composeArgs

$healthUrl = "http://localhost:$BackendPort/health"
Write-Host "Waiting for backend health on $healthUrl ..." -ForegroundColor Cyan
$health = Wait-ForHttp -Url $healthUrl
Write-Host "Backend is ready ($($health.status))." -ForegroundColor Green

Set-Location $frontendDir
if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
    Write-Host "Installing frontend dependencies with Bun..." -ForegroundColor Cyan
    & bun install

    if ($LASTEXITCODE -ne 0) {
        throw "bun install failed with exit code $LASTEXITCODE."
    }
}

Write-Host ""
Write-Host "Starting frontend dev server..." -ForegroundColor Cyan
Write-Host "Frontend: http://localhost:$FrontendPort" -ForegroundColor Green
Write-Host "Backend:  http://localhost:$BackendPort" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop frontend." -ForegroundColor Yellow

if ($StopBackendOnExit) {
    Write-Host "Backend containers will be stopped when this script exits." -ForegroundColor Yellow
}
else {
    Write-Host "Backend containers will keep running after script exit." -ForegroundColor Yellow
}

try {
    & bun run dev --host "127.0.0.1" --port $FrontendPort

    if ($LASTEXITCODE -ne 0) {
        throw "bun run dev failed with exit code $LASTEXITCODE."
    }
}
finally {
    if ($StopBackendOnExit) {
        Set-Location $repoRoot
        Write-Host ""
        Write-Host "Stopping backend containers..." -ForegroundColor Cyan
        Invoke-Compose -Args @("down")
    }
}
