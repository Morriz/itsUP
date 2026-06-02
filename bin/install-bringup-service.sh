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

# ── Host prerequisites ─────────────────────────────────────────────────────
# Pi-level state that itsUP services depend on. Idempotent — safe to re-run.

LOG_DIR="/var/log/instrukt-ai/itsup"
RESOLV_TAIL="/etc/resolvconf/resolv.conf.d/tail"
RESOLV_FALLBACK_LINE="nameserver 1.1.1.1"

echo "Ensuring ${LOG_DIR}..."
sudo mkdir -p "${LOG_DIR}"
sudo chown -R "${ITSUP_USER}:${ITSUP_GROUP}" "${LOG_DIR}"

echo "Ensuring host DNS fallback (${RESOLV_FALLBACK_LINE})..."
# Without this, an AdGuard outage takes host DNS down with it (ssh, cron,
# git fetch, this script itself). The primary nameserver in resolv.conf
# stays in place; this only adds a public fallback if not already present.
if [ -f "${RESOLV_TAIL}" ] && grep -qxF "${RESOLV_FALLBACK_LINE}" "${RESOLV_TAIL}"; then
  echo "  already present"
else
  echo "${RESOLV_FALLBACK_LINE}" | sudo tee -a "${RESOLV_TAIL}" >/dev/null
  sudo resolvconf -u
  echo "  added"
fi

echo "Ensuring host dnsmasq is absent..."
# Host dnsmasq is unused by current architecture (honeypot lives in proxynet;
# AdGuard owns LAN :53 when deployed). Leaving it installed = boot failure +
# misleading systemctl --failed marker.
if dpkg -s dnsmasq >/dev/null 2>&1; then
  sudo apt-get -y purge dnsmasq
  echo "  purged"
else
  echo "  not installed"
fi

echo ""
# ── End host prerequisites ──────────────────────────────────────────────────

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
