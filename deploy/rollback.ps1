# ==============================================================================
# DREAM DESTINY — POWERSHELL ROLLBACK SCRIPT (WINDOWS / LOCAL PARITY)
# ==============================================================================
# Reverts the microservice stack to a verified stable state and restores traffic
# immediately without manual intervention.
#
# Usage:
#   .\deploy\rollback.ps1 [TARGET_COMMIT_SHA]
# ==============================================================================

param(
    [string]$TargetCommit = ""
)

$ErrorActionPreference = "Stop"

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "    DREAM DESTINY — AUTONOMOUS PRODUCTION ROLLBACK ENGINE (PS)   " -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

$CurrentCommit = git rev-parse --short HEAD
Write-Host "[INFO] Current active commit: $CurrentCommit" -ForegroundColor Yellow

$StateFile = ".deploy_state/last_healthy_commit"
if ([string]::IsNullOrWhiteSpace($TargetCommit)) {
    if (Test-Path $StateFile) {
        $TargetCommit = (Get-Content $StateFile -Raw).Trim()
        Write-Host "[INFO] Target commit retrieved from state registry: $TargetCommit" -ForegroundColor Green
    } else {
        $TargetCommit = (git rev-parse --short HEAD~1).Trim()
        Write-Host "[WARN] No state registry found. Defaulting to previous git commit: $TargetCommit" -ForegroundColor Yellow
    }
}

if ($CurrentCommit -eq $TargetCommit) {
    Write-Host "[WARN] Target commit matches current. Reverting to HEAD~1..." -ForegroundColor Yellow
    $TargetCommit = (git rev-parse --short HEAD~1).Trim()
}

Write-Host "`n[1/4] Reverting git repository to target stable commit: $TargetCommit..." -ForegroundColor Cyan
git checkout $TargetCommit

Write-Host "`n[2/4] Redeploying container stack from stable state..." -ForegroundColor Cyan
docker compose -f docker-compose.prod.yml up -d --remove-orphans

Write-Host "`n[3/4] Cycling NGINX gateway to bind stable upstreams..." -ForegroundColor Cyan
docker compose -f docker-compose.prod.yml restart gateway
Start-Sleep -Seconds 3

Write-Host "`n[4/4] Verifying health and connectivity across all endpoints..." -ForegroundColor Cyan
python deploy/verify_deployment.py http://localhost --retries 5 --retry-delay 3

if ($LASTEXITCODE -eq 0) {
    Write-Host "==================================================================" -ForegroundColor Green
    Write-Host "[SUCCESS] Rollback completed! Traffic restored to commit $TargetCommit." -ForegroundColor Green
    Write-Host "==================================================================" -ForegroundColor Green
} else {
    Write-Host "==================================================================" -ForegroundColor Red
    Write-Host "[CRITICAL] Rollback verification reported errors. Inspect docker logs!" -ForegroundColor Red
    Write-Host "==================================================================" -ForegroundColor Red
    exit 1
}
