<#
.SYNOPSIS
    Automated Zero-Touch AWS CLI Provisioning Script for Dream Destiny Backend.
.DESCRIPTION
    Provisions a production-ready, AWS Free-Tier eligible EC2 instance (t3.micro),
    creates a hardened security group (only ports 22, 80, 443), generates an SSH key pair,
    and bootstraps Docker + NGINX reverse proxy + all 7 microservices automatically.
.EXAMPLE
    .\deploy\deploy_aws.ps1 -Region ap-south-1
#>

[CmdletBinding()]
param(
    [string]$Region = "",
    [string]$InstanceType = "t3.micro",
    [string]$KeyName = "dream-destiny-key",
    [string]$SecurityGroupName = "dream-destiny-sg",
    [string]$RepoUrl = "https://github.com/jashwanth-cse/DreamDestiny.git",
    [string]$Branch = "main",
    [string]$EnvFile = ".env"
)

$ErrorActionPreference = "Stop"

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "    DREAM DESTINY — AWS ZERO-TOUCH AUTOMATED DEPLOYMENT         " -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

# ── 1. Check AWS CLI & Authentication ─────────────────────────────────────────
Write-Host "`n[1/8] Checking AWS CLI installation and credentials..." -ForegroundColor Yellow
if (-not (Get-Command "aws" -ErrorAction SilentlyContinue)) {
    Write-Error "AWS CLI is not installed or not in PATH. Please install it from https://aws.amazon.com/cli/"
    exit 1
}

try {
    $caller = aws sts get-caller-identity --output json | ConvertFrom-Json
    Write-Host "[OK] Authenticated as AWS Account: $($caller.Account) (ARN: $($caller.Arn))" -ForegroundColor Green
} catch {
    Write-Error "AWS credentials are invalid or expired. Run 'aws configure' first."
    exit 1
}

# Resolve target region
if (-not $Region) {
    $Region = aws configure get region
    if (-not $Region) { $Region = "ap-south-1" }
}
Write-Host "[INFO] Target AWS Region: $Region" -ForegroundColor Cyan

# ── 2. Query Default VPC & Subnet ─────────────────────────────────────────────
Write-Host "`n[2/8] Querying default VPC and public subnet in $Region..." -ForegroundColor Yellow
$vpcJson = aws ec2 describe-vpcs --region $Region --filters "Name=isDefault,Values=true" --output json | ConvertFrom-Json
if (-not $vpcJson.Vpcs -or $vpcJson.Vpcs.Count -eq 0) {
    # Fallback to any available VPC
    $vpcJson = aws ec2 describe-vpcs --region $Region --output json | ConvertFrom-Json
}
$vpcId = $vpcJson.Vpcs[0].VpcId
Write-Host "[OK] Using VPC: $vpcId" -ForegroundColor Green

$subnetJson = aws ec2 describe-subnets --region $Region --filters "Name=vpc-id,Values=$vpcId" --output json | ConvertFrom-Json
$subnetId = $subnetJson.Subnets[0].SubnetId
Write-Host "[OK] Using Subnet: $subnetId" -ForegroundColor Green

# ── 3. Security Group Provisioning ────────────────────────────────────────────
Write-Host "`n[3/8] Configuring hardened Security Group ($SecurityGroupName)..." -ForegroundColor Yellow
$sgJson = aws ec2 describe-security-groups --region $Region --filters "Name=group-name,Values=$SecurityGroupName" "Name=vpc-id,Values=$vpcId" --output json | ConvertFrom-Json

if ($sgJson.SecurityGroups -and $sgJson.SecurityGroups.Count -gt 0) {
    $sgId = $sgJson.SecurityGroups[0].GroupId
    Write-Host "[OK] Found existing Security Group: $sgId" -ForegroundColor Green
} else {
    $createSg = aws ec2 create-security-group --region $Region --group-name $SecurityGroupName --description "Dream Destiny Gateway - Only SSH, HTTP, HTTPS" --vpc-id $vpcId --output json | ConvertFrom-Json
    $sgId = $createSg.GroupId
    Write-Host "[OK] Created Security Group: $sgId" -ForegroundColor Green

    # Detect caller's public IP for locked-down SSH
    $myIp = ""
    try {
        $myIp = (Invoke-RestMethod -Uri "https://checkip.amazonaws.com" -TimeoutSec 5).Trim()
    } catch {
        $myIp = ""
    }

    $sshCidr = if ($myIp) { "$myIp/32" } else { "0.0.0.0/0" }
    Write-Host "Authorizing Port 22 (SSH) from: $sshCidr" -ForegroundColor Cyan
    aws ec2 authorize-security-group-ingress --region $Region --group-id $sgId --protocol tcp --port 22 --cidr $sshCidr | Out-Null

    Write-Host "Authorizing Port 80 (HTTP) from: 0.0.0.0/0" -ForegroundColor Cyan
    aws ec2 authorize-security-group-ingress --region $Region --group-id $sgId --protocol tcp --port 80 --cidr 0.0.0.0/0 | Out-Null

    Write-Host "Authorizing Port 443 (HTTPS) from: 0.0.0.0/0" -ForegroundColor Cyan
    aws ec2 authorize-security-group-ingress --region $Region --group-id $sgId --protocol tcp --port 443 --cidr 0.0.0.0/0 | Out-Null

    Write-Host "[SECURITY] Ports 8000-8006 are strictly blocked from the public internet." -ForegroundColor Green
}

# ── 4. SSH Key Pair Generation ────────────────────────────────────────────────
Write-Host "`n[4/8] Setting up SSH Key Pair ($KeyName)..." -ForegroundColor Yellow
$keyCheck = aws ec2 describe-key-pairs --region $Region --filters "Name=key-name,Values=$KeyName" --output json | ConvertFrom-Json
$keyPath = Join-Path $PSScriptRoot "$KeyName.pem"

if ($keyCheck.KeyPairs -and $keyCheck.KeyPairs.Count -gt 0) {
    Write-Host "[OK] Key pair '$KeyName' already exists in AWS." -ForegroundColor Green
    if (-not (Test-Path $keyPath)) {
        Write-Host "[WARNING] Local file '$keyPath' not found. If you lost the private key, use another key or delete it in AWS first." -ForegroundColor Yellow
    }
} else {
    Write-Host "Generating new RSA key pair and saving to $keyPath..." -ForegroundColor Cyan
    $keyMaterial = aws ec2 create-key-pair --region $Region --key-name $KeyName --query "KeyMaterial" --output text
    [System.IO.File]::WriteAllText($keyPath, $keyMaterial, [System.Text.Encoding]::ASCII)
    Write-Host "[OK] Saved private key to $keyPath" -ForegroundColor Green
}

# ── 5. Resolve Ubuntu 24.04 LTS AMI ───────────────────────────────────────────
Write-Host "`n[5/8] Resolving latest official Ubuntu 24.04 LTS AMI in $Region..." -ForegroundColor Yellow
$amiId = ""
try {
    # Query AWS SSM Parameter Store for official Canonical Ubuntu AMI
    $ssmPath = "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
    $amiId = aws ssm get-parameter --region $Region --name $ssmPath --query "Parameter.Value" --output text
} catch {
    $amiId = ""
}

if (-not $amiId -or $amiId -eq "None") {
    # Fallback search via ec2 describe-images
    $imagesJson = aws ec2 describe-images --region $Region --owners 099720109477 `
        --filters "Name=name,Values=ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*" "Name=state,Values=available" `
        --query "sort_by(Images, &CreationDate)[-1].ImageId" --output text
    $amiId = $imagesJson.Trim()
}
Write-Host "[OK] Using AMI: $amiId (Ubuntu 24.04 LTS)" -ForegroundColor Green

# ── 6. Assemble Cloud-Init User Data Script ────────────────────────────────────
Write-Host "`n[6/8] Assembling automated bootstrap user-data script..." -ForegroundColor Yellow
$templatePath = Join-Path $PSScriptRoot "user_data.sh.template"
if (-not (Test-Path $templatePath)) {
    Write-Error "Template file $templatePath not found!"
    exit 1
}

$templateContent = Get-Content $templatePath -Raw

# Read .env content
$rootEnv = Join-Path (Split-Path $PSScriptRoot -Parent) ".env"
$envPath = if (Test-Path $EnvFile) { $EnvFile } elseif (Test-Path ".env") { ".env" } elseif (Test-Path "..\.env") { "..\.env" } elseif (Test-Path $rootEnv) { $rootEnv } else { "" }
$envContent = ""
if ($envPath) {
    Write-Host "Embedding environment variables from $envPath into cloud-init..." -ForegroundColor Cyan
    $envContent = Get-Content $envPath -Raw
} else {
    Write-Host "[WARNING] No .env file found. Using default empty template." -ForegroundColor Yellow
    $envContent = "# Auto-generated empty .env`nFRONTEND_ORIGIN=*`n"
}

$userDataScript = $templateContent.Replace("__REPO_URL__", $RepoUrl).Replace("__REPO_BRANCH__", $Branch).Replace("__ENV_CONTENT__", $envContent)
$userDataPath = Join-Path $PSScriptRoot "user_data.sh"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($userDataPath, $userDataScript, $utf8NoBom)
$userDataUri = "fileb://" + $userDataPath.Replace('\', '/')
Write-Host "[OK] Generated $userDataPath" -ForegroundColor Green

# ── 7. Launch EC2 Free Tier Instance ──────────────────────────────────────────
Write-Host "`n[7/8] Launching Free Tier EC2 instance ($InstanceType, 30 GB gp3 storage)..." -ForegroundColor Yellow

$blockDevice = "DeviceName=/dev/sda1,Ebs={VolumeSize=30,VolumeType=gp3,DeleteOnTermination=true}"
$tagSpecs = "ResourceType=instance,Tags=[{Key=Name,Value=dream-destiny-backend},{Key=Project,Value=DreamDestiny},{Key=Environment,Value=Production}]"

$runRaw = aws ec2 run-instances `
    --region $Region `
    --image-id $amiId `
    --instance-type $InstanceType `
    --key-name $KeyName `
    --security-group-ids $sgId `
    --subnet-id $subnetId `
    --user-data "$userDataUri" `
    --block-device-mappings "$blockDevice" `
    --tag-specifications "$tagSpecs" `
    --output json

if (-not $runRaw) {
    Write-Error "Failed to launch EC2 instance. Check AWS CLI output above."
    exit 1
}

$runJson = $runRaw | ConvertFrom-Json
$instanceId = $runJson.Instances[0].InstanceId
Write-Host "[OK] Instance launched: $instanceId" -ForegroundColor Green

Write-Host "Waiting for instance to enter 'running' state (takes ~15-20s)..." -ForegroundColor Cyan
aws ec2 wait instance-running --region $Region --instance-ids $instanceId

$instDesc = aws ec2 describe-instances --region $Region --instance-ids $instanceId --output json | ConvertFrom-Json
$publicIp = $instDesc.Reservations[0].Instances[0].PublicIpAddress
$publicDns = $instDesc.Reservations[0].Instances[0].PublicDnsName

# ── 8. Summary & Next Steps ───────────────────────────────────────────────────
Write-Host "`n=================================================================" -ForegroundColor Green
Write-Host "   DEPLOYMENT LAUNCHED SUCCESSFULLY!                            " -ForegroundColor Green
Write-Host "=================================================================" -ForegroundColor Green
Write-Host "  Instance ID   : $instanceId"
Write-Host "  Public IP     : $publicIp"
Write-Host "  Public DNS    : $publicDns"
Write-Host "  Unified URL   : http://$publicIp"
Write-Host "=================================================================" -ForegroundColor Green

Write-Host "`nAPI Endpoints (available via single entry point):" -ForegroundColor Cyan
Write-Host "  Health Check  : http://$publicIp/health"
Write-Host "  Planner (AI)  : http://$publicIp/plan"
Write-Host "  Tourism       : http://$publicIp/tourism?city=delhi"
Write-Host "  Hotels        : http://$publicIp/hotels?city=delhi"
Write-Host "  Trains        : http://$publicIp/api/v1/trains/search?from=delhi&to=mumbai&date=15-10-2026"
Write-Host "  Buses         : http://$publicIp/api/v1/buses/search?source=delhi&destination=jaipur&journey_date=15-10-2026"
Write-Host "  Flights       : http://$publicIp/flights/search"

Write-Host "`nSSH Access:" -ForegroundColor Cyan
Write-Host "  ssh -i `"$keyPath`" ubuntu@$publicIp"

Write-Host "`nMonitor Initial Bootstrap Progress:" -ForegroundColor Cyan
Write-Host "  ssh -i `"$keyPath`" ubuntu@$publicIp `"tail -f /var/log/dream-destiny-init.log`""

Write-Host "`nProduction SSL/HTTPS Setup (Cloudflare Free Tier):" -ForegroundColor Yellow
Write-Host "  1. Point an 'A' record (e.g. api.yourdomain.com) to $publicIp in Cloudflare DNS."
Write-Host "  2. Enable Cloudflare Proxy (Orange Cloud icon)."
Write-Host "  3. You will immediately have free SSL (https://api.yourdomain.com), DDoS protection, and edge caching!`n"
