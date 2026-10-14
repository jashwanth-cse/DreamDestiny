#!/usr/bin/env bash
# ==============================================================================
# DREAM DESTINY — PRODUCTION AUTOMATED & ON-DEMAND ROLLBACK SCRIPT
# ==============================================================================
# Reverts the microservice stack to a verified stable state and restores traffic
# immediately without manual intervention.
#
# Usage:
#   bash deploy/rollback.sh [TARGET_COMMIT_SHA]
# ==============================================================================

set -euo pipefail

DEPLOY_DIR="/opt/dream-destiny"
STATE_DIR="${DEPLOY_DIR}/.deploy_state"
STABLE_FILE="${STATE_DIR}/last_healthy_commit"

echo "=================================================================="
echo "    DREAM DESTINY — AUTONOMOUS PRODUCTION ROLLBACK ENGINE        "
echo "=================================================================="
echo "[INFO] Rollback execution initiated at: $(date -u)"

if [ ! -d "${DEPLOY_DIR}" ]; then
    DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi

cd "${DEPLOY_DIR}"

CURRENT_COMMIT=$(git rev-parse --short HEAD)
echo "[INFO] Current active commit: ${CURRENT_COMMIT}"

TARGET_COMMIT="${1:-}"

if [ -z "${TARGET_COMMIT}" ]; then
    if [ -f "${STABLE_FILE}" ]; then
        TARGET_COMMIT=$(cat "${STABLE_FILE}")
        echo "[INFO] Target commit retrieved from state registry: ${TARGET_COMMIT}"
    else
        TARGET_COMMIT=$(git rev-parse --short HEAD~1)
        echo "[WARN] No state registry found. Defaulting to previous git commit: ${TARGET_COMMIT}"
    fi
fi

if [ "${CURRENT_COMMIT}" == "${TARGET_COMMIT}" ]; then
    echo "[WARN] Target commit matches currently running commit. Forcing rollback to HEAD~1..."
    TARGET_COMMIT=$(git rev-parse --short HEAD~1)
fi

echo -e "\n[1/4] Reverting git repository to target stable commit: ${TARGET_COMMIT}..."
git checkout "${TARGET_COMMIT}" || git reset --hard "${TARGET_COMMIT}"

echo -e "\n[2/4] Redeploying container stack from stable state..."
docker compose -f docker-compose.prod.yml up -d --remove-orphans

echo -e "\n[3/4] Cycling NGINX gateway to bind stable upstreams..."
docker compose -f docker-compose.prod.yml restart gateway
sleep 3

echo -e "\n[4/4] Verifying health and connectivity across all endpoints..."
if python3 deploy/verify_deployment.py http://localhost --retries 5 --retry-delay 3; then
    echo "=================================================================="
    echo "[SUCCESS] Rollback completed! Traffic restored to commit ${TARGET_COMMIT}."
    echo "=================================================================="
    exit 0
else
    echo "=================================================================="
    echo "[CRITICAL] Rollback verification reported errors. Inspect docker logs!"
    echo "=================================================================="
    exit 1
fi
