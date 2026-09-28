# ==============================================================================
# Dream Destiny - Sync Local .env to AWS EC2 & Restart Service
# ==============================================================================
# Usage:
#   .\deploy\sync_env.ps1
#   .\deploy\sync_env.ps1 -Service whatsapp-bot-service
#   .\deploy\sync_env.ps1 -Service all
# ==============================================================================

param (
    [string]$Service = "whatsapp-bot-service",
    [string]$Ec2Host = "3.110.43.124",
    [string]$Ec2User = "ubuntu",
    [string]$KeyPath = "deploy/dream-destiny-key.pem",
    [string]$RemoteDir = "/opt/dream-destiny"
)

$ErrorActionPreference = "Stop"

Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "  DREAM DESTINY - EC2 ENV SYNC & RELOAD" -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan

# 1. Check prerequisite files
if (-not (Test-Path -Path ".env")) {
    Write-Host "[ERROR] Local .env file not found in root directory!" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path -Path $KeyPath)) {
    Write-Host "[ERROR] SSH Key not found at $KeyPath!" -ForegroundColor Red
    exit 1
}

# 2. Upload .env to EC2
Write-Host "[1/3] Uploading local .env to EC2 ($Ec2Host)..." -ForegroundColor Yellow
scp -i $KeyPath -o StrictHostKeyChecking=no ".env" "${Ec2User}@${Ec2Host}:${RemoteDir}/.env"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to upload .env via SCP." -ForegroundColor Red
    exit 1
}
Write-Host "       .env uploaded successfully!" -ForegroundColor Green

# 3. Reload container(s) on EC2
if ($Service -eq "all") {
    Write-Host "[2/3] Recreating and reloading ALL containers..." -ForegroundColor Yellow
    ssh -i $KeyPath -o StrictHostKeyChecking=no "${Ec2User}@${Ec2Host}" "cd $RemoteDir && docker compose -f docker-compose.prod.yml up -d"
} else {
    Write-Host "[2/3] Recreating and reloading service: $Service..." -ForegroundColor Yellow
    ssh -i $KeyPath -o StrictHostKeyChecking=no "${Ec2User}@${Ec2Host}" "cd $RemoteDir && docker compose -f docker-compose.prod.yml up -d $Service"
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to restart service on EC2." -ForegroundColor Red
    exit 1
}

# 4. Check Health / Status
Write-Host "[3/3] Checking container status..." -ForegroundColor Yellow
ssh -i $KeyPath -o StrictHostKeyChecking=no "${Ec2User}@${Ec2Host}" "docker ps --filter name=$Service --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"

Write-Host "`n[SUCCESS] Environment synced and $Service successfully reloaded!" -ForegroundColor Green
