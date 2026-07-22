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

# Refuse to run from a linked git worktree — this installs systemd/launchd units
# carrying absolute repo paths; they must bind the canonical checkout.
GUARD_OP="make install-runtime"
. "${REPO_ROOT}/bin/lib/assert-canonical-checkout.sh"
PYTHONPATH="${REPO_ROOT}" "${REPO_ROOT}/.venv/bin/python" -c "from lib.host_gate import require_host; require_host('make install-runtime')"

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

assert_dnsmasq_absent_linux() {
  # Host dnsmasq is unused by current architecture (honeypot lives in proxynet;
  # AdGuard owns LAN :53 when deployed). Leaving it installed = boot failure
  # against docker0 + misleading systemctl --failed marker. The installer only
  # asserts the invariant; removal is an operator action.
  if command -v dpkg >/dev/null 2>&1 && dpkg -s dnsmasq >/dev/null 2>&1; then
    echo "ERROR: host dnsmasq is installed; it conflicts with the itsUP DNS architecture." >&2
    echo "Remove it first: sudo apt-get -y purge dnsmasq" >&2
    exit 1
  fi
}

ensure_host_prereqs() {
  if [ "${PLATFORM}" = "linux" ]; then
    assert_dnsmasq_absent_linux
    ensure_dns_fallback_linux
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

# Writes the rendered template only if it differs from what's on disk.
# Returns 0 if it wrote (changed), 1 if unchanged (skipped), 2 if the render
# or write itself failed. Call sites must capture the exit status via
# `write_if_changed ... || rc=$?` (not `if write_if_changed ...; then`) — the
# bare/if-tested form exempts the whole function from `set -e`, so a
# non-error rc=1 is fine, but wrapping it in `if` again silently swallows a
# real rc=2 write failure.
write_if_changed() {
  local template_file="$1"
  local dest_path="$2"
  local use_sudo="${3:-false}"

  if [ ! -r "${template_file}" ]; then
    echo "ERROR: template not readable: ${template_file}" >&2
    return 2
  fi

  if [ -f "${dest_path}" ] && render_template "${template_file}" | cmp -s - "${dest_path}"; then
    echo "  ${dest_path} unchanged, skipping"
    return 1
  fi

  echo "Writing ${dest_path}..."
  local render_rc write_rc
  local -a pipeline_status
  if [ "${use_sudo}" = "true" ]; then
    render_template "${template_file}" | sudo tee "${dest_path}" >/dev/null
    pipeline_status=("${PIPESTATUS[@]}")
    render_rc=${pipeline_status[0]}
    write_rc=${pipeline_status[1]}
  else
    render_template "${template_file}" > "${dest_path}"
    render_rc=$?
    write_rc=0
  fi

  if [ "${render_rc}" -ne 0 ] || [ "${write_rc}" -ne 0 ]; then
    echo "ERROR: failed to write ${dest_path}" >&2
    return 2
  fi
  return 0
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

  local bringup_changed=false
  for unit in "${units[@]}"; do
    local write_rc=0
    write_if_changed "${TEMPLATE_DIR}/${unit}" "${SERVICE_DIR}/${unit}" true || write_rc=$?
    if [ "${write_rc}" -eq 2 ]; then
      echo "ERROR: aborting install — failed to write ${SERVICE_DIR}/${unit}" >&2
      exit 1
    fi
    if [ "${write_rc}" -eq 0 ] && [ "${unit}" = "itsup-bringup.service" ]; then
      bringup_changed=true
    fi
  done

  echo "Reloading systemd..."
  sudo systemctl daemon-reload

  sudo systemctl enable itsup-bringup.service
  if [ "${bringup_changed}" = "true" ] || ! systemctl is-active --quiet itsup-bringup.service; then
    sudo systemctl restart itsup-bringup.service
  else
    echo "  itsup-bringup.service unchanged and active, skipping restart"
  fi
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
  # No healthcheck agent on macOS: bin/pi-healthcheck.sh is Linux-only
  # (reads /proc, calls systemctl, hardcodes su -l <user>) and would die
  # every 5 min under set -euo pipefail. Add a Darwin-capable check before
  # reintroducing an ai.itsup.healthcheck.plist.
  local agents=(
    "ai.itsup.bringup"
    "ai.itsup.apply"
    "ai.itsup.backup"
  )

  mkdir -p "${SERVICE_DIR}"
  local domain="gui/$(id -u "${ITSUP_USER}")"

  for label in "${agents[@]}"; do
    local plist="${SERVICE_DIR}/${label}.plist"
    local template="${TEMPLATE_DIR}/${label}.plist"

    local write_rc=0
    write_if_changed "${template}" "${plist}" || write_rc=$?
    if [ "${write_rc}" -eq 2 ]; then
      echo "ERROR: aborting install — failed to write ${plist}" >&2
      exit 1
    fi
    local plist_changed=true
    if [ "${write_rc}" -eq 1 ]; then
      plist_changed=false
    fi

    if [ "${label}" = "ai.itsup.bringup" ] && [ "${plist_changed}" = "false" ] \
      && launchctl print "${domain}/${label}" >/dev/null 2>&1; then
      echo "  ${label} unchanged and loaded, skipping reload"
      continue
    fi

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
}

# ── Dispatch ───────────────────────────────────────────────────────────────

ensure_host_prereqs

case "${PLATFORM}" in
  linux) install_systemd_units;;
  macos) install_launchd_agents;;
esac
