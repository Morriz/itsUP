#!/usr/bin/env bash
set -euo pipefail

# Installs the itsUP bringup/apply/backup/healthcheck services on the host.
# Cross-platform: systemd units on Linux, launchd agents on macOS. Idempotent.
#
# Defaults adapt to whoever runs the script and wherever the repo lives;
# every default can be overridden via env for non-standard layouts:
#   ITSUP_USER, ITSUP_GROUP, ITSUP_ROOT,
#   SERVICE_DIR (Linux: /etc/systemd/system; macOS: ~/Library/LaunchAgents)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

ITSUP_USER="${ITSUP_USER:-${USER:-$(id -un)}}"
ITSUP_GROUP="${ITSUP_GROUP:-$(id -gn "${ITSUP_USER}")}"
ITSUP_ROOT="${ITSUP_ROOT:-${REPO_ROOT}}"
ITSUP_HOME="${HOME:-/Users/${ITSUP_USER}}"

# ── Platform detection ─────────────────────────────────────────────────────

case "$(uname -s)" in
  Darwin*) PLATFORM="macos";;
  Linux*)  PLATFORM="linux";;
  *)       echo "Unsupported platform: $(uname -s)" >&2; exit 1;;
esac

if [ "${PLATFORM}" = "macos" ]; then
  TEMPLATE_DIR="${REPO_ROOT}/samples/launchd"
  SERVICE_DIR="${SERVICE_DIR:-${ITSUP_HOME}/Library/LaunchAgents}"
else
  TEMPLATE_DIR="${REPO_ROOT}/samples/systemd"
  SERVICE_DIR="${SERVICE_DIR:-/etc/systemd/system}"
fi

# ── Host prerequisites ─────────────────────────────────────────────────────
# Host-level state itsUP services depend on. Idempotent and target-adaptive:
# every step detects whether it applies on this host and no-ops cleanly when not.

LOG_DIR="/var/log/instrukt-ai/itsup"

ensure_log_dir() {
  echo "Ensuring ${LOG_DIR}..."
  sudo mkdir -p "${LOG_DIR}"
  sudo chown -R "${ITSUP_USER}:${ITSUP_GROUP}" "${LOG_DIR}"
}

ensure_dns_fallback_linux() {
  # Adds a public-DNS fallback so the host keeps resolving when its primary
  # local DNS (AdGuard / dnsmasq / etc.) is down. The primary stays first;
  # the fallback is only consulted when the primary doesn't answer.
  # Linux-only: macOS uses SystemConfiguration; if a Mac becomes a local-DNS
  # host we can add a `networksetup`-based variant.
  local fallback="1.1.1.1 9.9.9.9"
  local primary="1.1.1.1"

  echo "Ensuring host DNS fallback (${primary})..."

  if systemctl is-active --quiet systemd-resolved 2>/dev/null; then
    local conf=/etc/systemd/resolved.conf
    if grep -qE "^FallbackDNS=.*${primary}" "${conf}" 2>/dev/null; then
      echo "  systemd-resolved: already configured"
    else
      if grep -qE "^#?FallbackDNS=" "${conf}" 2>/dev/null; then
        sudo sed -i -E "s|^#?FallbackDNS=.*|FallbackDNS=${fallback}|" "${conf}"
      else
        echo "FallbackDNS=${fallback}" | sudo tee -a "${conf}" >/dev/null
      fi
      sudo systemctl restart systemd-resolved
      echo "  systemd-resolved: configured"
    fi
    return
  fi

  if command -v resolvconf >/dev/null 2>&1 && [ -d /etc/resolvconf/resolv.conf.d ]; then
    local tail_file=/etc/resolvconf/resolv.conf.d/tail
    local line="nameserver ${primary}"
    if [ -f "${tail_file}" ] && grep -qxF "${line}" "${tail_file}"; then
      echo "  resolvconf: already configured"
    else
      echo "${line}" | sudo tee -a "${tail_file}" >/dev/null
      sudo resolvconf -u
      echo "  resolvconf: configured"
    fi
    return
  fi

  echo "  warning: no known resolver manager (systemd-resolved/resolvconf) detected — configure a DNS fallback manually per README"
}

ensure_dnsmasq_absent_linux() {
  # Host dnsmasq is unused by current architecture (honeypot lives in proxynet;
  # AdGuard owns LAN :53 when deployed). Leaving it installed = boot failure
  # against docker0 + misleading systemctl --failed marker. apt-aware; no-op
  # on non-Debian hosts.
  echo "Ensuring host dnsmasq is absent..."
  if ! command -v dpkg >/dev/null 2>&1; then
    echo "  not a Debian-family host; skipping"
    return
  fi
  if dpkg -s dnsmasq >/dev/null 2>&1; then
    sudo apt-get -y purge dnsmasq
    echo "  purged"
  else
    echo "  not installed"
  fi
}

ensure_host_prereqs() {
  ensure_log_dir
  if [ "${PLATFORM}" = "linux" ]; then
    ensure_dns_fallback_linux
    ensure_dnsmasq_absent_linux
  fi
  echo ""
}

# ── Template rendering ─────────────────────────────────────────────────────

render_template() {
  local template_file="$1"
  sed \
    -e "s|{{USER}}|${ITSUP_USER}|g" \
    -e "s|{{GROUP}}|${ITSUP_GROUP}|g" \
    -e "s|{{ROOT}}|${ITSUP_ROOT}|g" \
    -e "s|{{HOME}}|${ITSUP_HOME}|g" \
    "${template_file}"
}

# ── systemd (Linux) ────────────────────────────────────────────────────────

install_systemd_units() {
  local units=(
    "itsup-bringup.service"
    "itsup-apply.service"
    "itsup-apply.timer"
    "itsup-backup.service"
    "itsup-backup.timer"
    "pi-healthcheck.service"
    "pi-healthcheck.timer"
  )

  for unit in "${units[@]}"; do
    echo "Writing ${SERVICE_DIR}/${unit}..."
    render_template "${TEMPLATE_DIR}/${unit}" | sudo tee "${SERVICE_DIR}/${unit}" >/dev/null
  done

  echo "Reloading systemd..."
  sudo systemctl daemon-reload

  sudo systemctl enable itsup-bringup.service
  sudo systemctl restart itsup-bringup.service
  sudo systemctl enable --now itsup-apply.timer
  sudo systemctl enable --now itsup-backup.timer
  sudo systemctl enable --now pi-healthcheck.timer

  echo "✓ itsup-bringup.service installed and started"
  echo "✓ itsup-apply.timer enabled (03:00 nightly apply)"
  echo "✓ itsup-backup.timer enabled (05:00 nightly backup)"
  echo "✓ pi-healthcheck.timer enabled (every 5 minutes)"
}

# ── launchd (macOS) ────────────────────────────────────────────────────────

install_launchd_agents() {
  local agents=(
    "ai.itsup.bringup"
    "ai.itsup.apply"
    "ai.itsup.backup"
    "ai.itsup.healthcheck"
  )

  mkdir -p "${SERVICE_DIR}"
  local domain="gui/$(id -u "${ITSUP_USER}")"

  for label in "${agents[@]}"; do
    local plist="${SERVICE_DIR}/${label}.plist"
    local template="${TEMPLATE_DIR}/${label}.plist"
    echo "Writing ${plist}..."
    render_template "${template}" > "${plist}"

    # Reload: bootout (modern unload) || unload (legacy) || true; then bootstrap || load.
    launchctl bootout "${domain}" "${plist}" 2>/dev/null \
      || launchctl unload "${plist}" 2>/dev/null || true
    if ! launchctl bootstrap "${domain}" "${plist}" 2>/dev/null; then
      launchctl load "${plist}"
    fi
  done

  echo "✓ ai.itsup.bringup loaded (runs at load)"
  echo "✓ ai.itsup.apply loaded (03:00 nightly apply)"
  echo "✓ ai.itsup.backup loaded (05:00 nightly backup)"
  echo "✓ ai.itsup.healthcheck loaded (every 5 minutes)"
}

# ── Dispatch ───────────────────────────────────────────────────────────────

ensure_host_prereqs

case "${PLATFORM}" in
  linux) install_systemd_units;;
  macos) install_launchd_agents;;
esac
