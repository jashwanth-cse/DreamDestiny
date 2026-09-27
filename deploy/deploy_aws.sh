#!/usr/bin/env bash
# ==============================================================================
# DREAM DESTINY — ZERO-TOUCH AWS CLI PROVISIONING SCRIPT (BASH)
# ==============================================================================
# Provisions an AWS Free-Tier eligible EC2 instance (t3.micro), configures a
# hardened security group, generates SSH keys, and bootstraps Docker + NGINX.
#
# Usage:
#   chmod +x deploy/deploy_aws.sh
#   ./deploy/deploy_aws.sh [REGION] [INSTANCE_TYPE]
# ==============================================================================

set -euo pipefail

REGION="${1:-$(aws configure get region || echo 'ap-south-1')}"
INSTANCE_TYPE="${2:-t3.micro}"
KEY_NAME="dream-destiny-key"
SG_NAME="dream-destiny-sg"
REPO_URL="https://github.com/jashwanth-cse/DreamDestiny.git"
REPO_BRANCH="main"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "================================================================="
echo "   DREAM DESTINY — AWS ZERO-TOUCH AUTOMATED DEPLOYMENT (BASH)    "
echo "================================================================="
echo "[INFO] Target AWS Region: ${REGION}"
echo "[INFO] Instance Type    : ${INSTANCE_TYPE} (AWS Free Tier eligible)"

# ── 1. Check AWS CLI & Authentication ─────────────────────────────────────────
echo -e "\n[1/8] Checking AWS CLI installation and credentials..."
if ! command -v aws &> /dev/null; then
    echo "[ERROR] AWS CLI is not installed. Install from https://aws.amazon.com/cli/"
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text)
echo "[OK] Authenticated with AWS Account: ${ACCOUNT_ID}"

# ── 2. Query Default VPC & Subnet ─────────────────────────────────────────────
echo -e "\n[2/8] Querying default VPC and public subnet in ${REGION}..."
VPC_ID=$(aws ec2 describe-vpcs --region "${REGION}" --filters "Name=isDefault,Values=true" --query "Vpcs[0].VpcId" --output text)
if [ "${VPC_ID}" == "None" ] || [ -z "${VPC_ID}" ]; then
    VPC_ID=$(aws ec2 describe-vpcs --region "${REGION}" --query "Vpcs[0].VpcId" --output text)
fi
echo "[OK] Using VPC: ${VPC_ID}"

SUBNET_ID=$(aws ec2 describe-subnets --region "${REGION}" --filters "Name=vpc-id,Values=${VPC_ID}" --query "Subnets[0].SubnetId" --output text)
echo "[OK] Using Subnet: ${SUBNET_ID}"

# ── 3. Security Group Provisioning ────────────────────────────────────────────
echo -e "\n[3/8] Configuring hardened Security Group (${SG_NAME})..."
SG_ID=$(aws ec2 describe-security-groups --region "${REGION}" --filters "Name=group-name,Values=${SG_NAME}" "Name=vpc-id,Values=${VPC_ID}" --query "SecurityGroups[0].GroupId" --output text || true)

if [ "${SG_ID}" != "None" ] && [ -n "${SG_ID}" ]; then
    echo "[OK] Found existing Security Group: ${SG_ID}"
else
    SG_ID=$(aws ec2 create-security-group --region "${REGION}" --group-name "${SG_NAME}" --description "Dream Destiny Gateway - Only SSH, HTTP, HTTPS" --vpc-id "${VPC_ID}" --query "GroupId" --output text)
    echo "[OK] Created Security Group: ${SG_ID}"

    # Lock down SSH to deployer IP
    MY_IP=$(curl -s https://checkip.amazonaws.com || echo "")
    SSH_CIDR="0.0.0.0/0"
    if [ -n "${MY_IP}" ]; then
        SSH_CIDR="${MY_IP}/32"
    fi
    echo "Authorizing Port 22 (SSH) from: ${SSH_CIDR}"
    aws ec2 authorize-security-group-ingress --region "${REGION}" --group-id "${SG_ID}" --protocol tcp --port 22 --cidr "${SSH_CIDR}" > /dev/null

    echo "Authorizing Port 80 (HTTP) from: 0.0.0.0/0"
    aws ec2 authorize-security-group-ingress --region "${REGION}" --group-id "${SG_ID}" --protocol tcp --port 80 --cidr 0.0.0.0/0 > /dev/null

    echo "Authorizing Port 443 (HTTPS) from: 0.0.0.0/0"
    aws ec2 authorize-security-group-ingress --region "${REGION}" --group-id "${SG_ID}" --protocol tcp --port 443 --cidr 0.0.0.0/0 > /dev/null

    echo "[SECURITY] Ports 8000-8006 are strictly blocked from the public internet."
fi

# ── 4. SSH Key Pair Generation ────────────────────────────────────────────────
echo -e "\n[4/8] Setting up SSH Key Pair (${KEY_NAME})..."
KEY_PATH="${SCRIPT_DIR}/${KEY_NAME}.pem"
KEY_EXISTS=$(aws ec2 describe-key-pairs --region "${REGION}" --filters "Name=key-name,Values=${KEY_NAME}" --query "KeyPairs[0].KeyName" --output text || true)

if [ "${KEY_EXISTS}" != "None" ] && [ -n "${KEY_EXISTS}" ]; then
    echo "[OK] Key pair '${KEY_NAME}' already exists in AWS."
else
    echo "Generating new RSA key pair and saving to ${KEY_PATH}..."
    aws ec2 create-key-pair --region "${REGION}" --key-name "${KEY_NAME}" --query "KeyMaterial" --output text > "${KEY_PATH}"
    chmod 400 "${KEY_PATH}"
    echo "[OK] Saved private key to ${KEY_PATH}"
fi

# ── 5. Resolve Ubuntu 24.04 LTS AMI ───────────────────────────────────────────
echo -e "\n[5/8] Resolving latest official Ubuntu 24.04 LTS AMI in ${REGION}..."
AMI_ID=$(aws ssm get-parameter --region "${REGION}" --name "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id" --query "Parameter.Value" --output text 2>/dev/null || echo "")

if [ -z "${AMI_ID}" ] || [ "${AMI_ID}" == "None" ]; then
    AMI_ID=$(aws ec2 describe-images --region "${REGION}" --owners 099720109477 \
        --filters "Name=name,Values=ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*" "Name=state,Values=available" \
        --query "sort_by(Images, &CreationDate)[-1].ImageId" --output text)
fi
echo "[OK] Using AMI: ${AMI_ID} (Ubuntu 24.04 LTS)"

# ── 6. Assemble Cloud-Init User Data Script ────────────────────────────────────
echo -e "\n[6/8] Assembling automated bootstrap user-data script..."
ENV_FILE="${SCRIPT_DIR}/../.env"
ENV_CONTENT=""
if [ -f "${ENV_FILE}" ]; then
    echo "Embedding environment variables from ${ENV_FILE} into cloud-init..."
    ENV_CONTENT=$(cat "${ENV_FILE}")
else
    echo "[WARNING] No .env file found. Using default empty template."
    ENV_CONTENT="FRONTEND_ORIGIN=*"
fi

USER_DATA_FILE="${SCRIPT_DIR}/user_data.sh"
cp "${SCRIPT_DIR}/user_data.sh.template" "${USER_DATA_FILE}"

# Safe replacement
python3 -c "
import sys
template = open('${SCRIPT_DIR}/user_data.sh.template').read()
replaced = template.replace('__REPO_URL__', '${REPO_URL}').replace('__REPO_BRANCH__', '${REPO_BRANCH}').replace('__ENV_CONTENT__', '''${ENV_CONTENT}''')
open('${USER_DATA_FILE}', 'w').write(replaced)
"
echo "[OK] Generated ${USER_DATA_FILE}"

# ── 7. Launch EC2 Free Tier Instance ──────────────────────────────────────────
echo -e "\n[7/8] Launching Free Tier EC2 instance (${INSTANCE_TYPE}, 30 GB gp3 storage)..."
INSTANCE_ID=$(aws ec2 run-instances \
    --region "${REGION}" \
    --image-id "${AMI_ID}" \
    --instance-type "${INSTANCE_TYPE}" \
    --key-name "${KEY_NAME}" \
    --security-group-ids "${SG_ID}" \
    --subnet-id "${SUBNET_ID}" \
    --user-data "fileb://${USER_DATA_FILE}" \
    --block-device-mappings "DeviceName=/dev/sda1,Ebs={VolumeSize=30,VolumeType=gp3,DeleteOnTermination=true}" \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=dream-destiny-backend},{Key=Project,Value=DreamDestiny},{Key=Environment,Value=Production}]" \
    --query "Instances[0].InstanceId" --output text)

echo "[OK] Instance launched: ${INSTANCE_ID}"
echo "Waiting for instance to enter 'running' state (takes ~15-20s)..."
aws ec2 wait instance-running --region "${REGION}" --instance-ids "${INSTANCE_ID}"

PUBLIC_IP=$(aws ec2 describe-instances --region "${REGION}" --instance-ids "${INSTANCE_ID}" --query "Reservations[0].Instances[0].PublicIpAddress" --output text)
PUBLIC_DNS=$(aws ec2 describe-instances --region "${REGION}" --instance-ids "${INSTANCE_ID}" --query "Reservations[0].Instances[0].PublicDnsName" --output text)

# ── 8. Summary & Next Steps ───────────────────────────────────────────────────
echo -e "\n================================================================="
echo "   DEPLOYMENT LAUNCHED SUCCESSFULLY!                            "
echo "================================================================="
echo "  Instance ID   : ${INSTANCE_ID}"
echo "  Public IP     : ${PUBLIC_IP}"
echo "  Public DNS    : ${PUBLIC_DNS}"
echo "  Unified URL   : http://${PUBLIC_IP}"
echo "================================================================="

echo -e "\nAPI Endpoints (available via single entry point):"
echo "  Health Check  : http://${PUBLIC_IP}/health"
echo "  Planner (AI)  : http://${PUBLIC_IP}/plan"
echo "  Tourism       : http://${PUBLIC_IP}/tourism?city=delhi"
echo "  Hotels        : http://${PUBLIC_IP}/hotels?city=delhi"
echo "  Trains        : http://${PUBLIC_IP}/api/v1/trains/search?from=delhi&to=mumbai&date=15-10-2026"
echo "  Buses         : http://${PUBLIC_IP}/api/v1/buses/search?source=delhi&destination=jaipur&journey_date=15-10-2026"
echo "  Flights       : http://${PUBLIC_IP}/flights/search"

echo -e "\nSSH Access:"
echo "  ssh -i \"${KEY_PATH}\" ubuntu@${PUBLIC_IP}"

echo -e "\nMonitor Initial Bootstrap Progress:"
echo "  ssh -i \"${KEY_PATH}\" ubuntu@${PUBLIC_IP} \"tail -f /var/log/dream-destiny-init.log\""
