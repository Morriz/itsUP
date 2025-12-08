#!/usr/bin/env bash
set -euo pipefail

# Defaults can be overridden via env:
#   ITSUP_USER, ITSUP_GROUP, ITSUP_ROOT, SERVICE_DIR

ITSUP_USER="${ITSUP_USER:-morriz}"
ITSUP_GROUP="${ITSUP_GROUP:-${ITSUP_USER}}"
ITSUP_ROOT="${ITSUP_ROOT:-/home/${ITSUP_USER}/srv}"
SERVICE_DIR="${SERVICE_DIR:-/etc/systemd/system}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TEMPLATE_DIR="${REPO_ROOT}/samples/systemd"

SERVICE_PATH="${SERVICE_DIR}/itsup-bringup.service"
APPLY_SERVICE_PATH="${SERVICE_DIR}/itsup-apply.service"
APPLY_TIMER_PATH="${SERVICE_DIR}/itsup-apply.timer"
BACKUP_SERVICE_PATH="${SERVICE_DIR}/itsup-backup.service"
BACKUP_TIMER_PATH="${SERVICE_DIR}/itsup-backup.timer"
HC_SERVICE_PATH="${SERVICE_DIR}/pi-healthcheck.service"
HC_TIMER_PATH="${SERVICE_DIR}/pi-healthcheck.timer"

render_template() {
  local template_file="$1"
  sed \
    -e "s|{{USER}}|${ITSUP_USER}|g" \
    -e "s|{{GROUP}}|${ITSUP_GROUP}|g" \
    -e "s|{{ROOT}}|${ITSUP_ROOT}|g" \
    "${template_file}"
}

echo "Writing ${SERVICE_PATH}..."
render_template "${TEMPLATE_DIR}/itsup-bringup.service" | sudo tee "${SERVICE_PATH}" >/dev/null

echo "Writing ${APPLY_SERVICE_PATH}..."
render_template "${TEMPLATE_DIR}/itsup-apply.service" | sudo tee "${APPLY_SERVICE_PATH}" >/dev/null

echo "Writing ${APPLY_TIMER_PATH}..."
render_template "${TEMPLATE_DIR}/itsup-apply.timer" | sudo tee "${APPLY_TIMER_PATH}" >/dev/null

echo "Writing ${BACKUP_SERVICE_PATH}..."
render_template "${TEMPLATE_DIR}/itsup-backup.service" | sudo tee "${BACKUP_SERVICE_PATH}" >/dev/null

echo "Writing ${BACKUP_TIMER_PATH}..."
render_template "${TEMPLATE_DIR}/itsup-backup.timer" | sudo tee "${BACKUP_TIMER_PATH}" >/dev/null

echo "Writing ${HC_SERVICE_PATH}..."
render_template "${TEMPLATE_DIR}/pi-healthcheck.service" | sudo tee "${HC_SERVICE_PATH}" >/dev/null

echo "Writing ${HC_TIMER_PATH}..."
render_template "${TEMPLATE_DIR}/pi-healthcheck.timer" | sudo tee "${HC_TIMER_PATH}" >/dev/null

echo "Reloading systemd..."
sudo systemctl daemon-reload

echo "Enabling itsup-bringup.service..."
sudo systemctl enable itsup-bringup.service

echo "Restarting itsup-bringup.service..."
sudo systemctl restart itsup-bringup.service

echo "Enabling itsup-apply.timer..."
sudo systemctl enable --now itsup-apply.timer

echo "Enabling itsup-backup.timer..."
sudo systemctl enable --now itsup-backup.timer

echo "Enabling pi-healthcheck.timer..."
sudo systemctl enable --now pi-healthcheck.timer

echo "✓ itsup-bringup.service installed and started"
echo "✓ itsup-apply.timer enabled (03:00 nightly apply)"
echo "✓ itsup-backup.timer enabled (05:00 nightly backup)"
echo "✓ pi-healthcheck.timer enabled (every 5 minutes)"
