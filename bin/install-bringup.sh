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
  SYSCTL_TEMPLATE="${REPO_ROOT}/samples/sysctl/99-itsup-nonlocal-bind.conf"
  SYSCTL_DEST="${SYSCTL_DEST:-/etc/sysctl.d/99-itsup-nonlocal-bind.conf}"
  SYSCTL_STATE_FILE="${ITSUP_ROOT}/.itsup-nonlocal-bind-state"
  SYSCTL_STATE_CONTENT_FILE="${ITSUP_ROOT}/.itsup-nonlocal-bind-state.content"
fi

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

# Systemd units this script installs; shared by install_systemd_units and
# --check-drift so the two can never compare against divergent lists.
SYSTEMD_UNITS=(
  "itsup-bringup.service"
  "itsup-apply.service"
  "itsup-apply.timer"
  "itsup-backup.service"
  "itsup-backup.timer"
  "pi-healthcheck.service"
  "pi-healthcheck.timer"
  "itsup-api.service"
  "itsup-monitor.service"
  "itsup-alert@.service"
)

# Renders each systemd unit template and compares it to the installed file at
# SERVICE_DIR. Read-only: no write, no daemon-reload, no host mutation of any
# kind. Templates are sourced solely from REPO_ROOT/samples/systemd (never the
# platform-selected TEMPLATE_DIR, which has no env override) so a webhook-
# controlled environment cannot redirect the trusted comparison inputs.
# stdout carries only the identities of drifted units, one per line, and only
# when the comparison completed cleanly (exit 0). A non-zero exit means the
# checker itself failed (unreadable template, or an installed path that
# exists but is not a regular file) — distinct from drift and never printed
# to stdout, so callers must not treat a non-zero exit as "no drift".
check_drift() {
  local drift_template_dir="${REPO_ROOT}/samples/systemd"
  local unit template_file dest_path
  local had_error=false
  local -a drifted=()

  for unit in "${SYSTEMD_UNITS[@]}"; do
    template_file="${drift_template_dir}/${unit}"
    dest_path="${SERVICE_DIR}/${unit}"

    if [ -e "${dest_path}" ] && [ ! -f "${dest_path}" ]; then
      echo "ERROR: ${dest_path} exists but is not a regular file" >&2
      had_error=true
      continue
    fi

    if [ ! -r "${template_file}" ]; then
      echo "ERROR: template not readable: ${template_file}" >&2
      had_error=true
      continue
    fi

    if [ ! -e "${dest_path}" ]; then
      drifted+=("${unit}")
      continue
    fi

    # Captured, not folded into a bare `if ! ... | cmp ...`: pipefail's
    # rightmost-nonzero rule would otherwise mask a render failure behind
    # cmp's own exit, and any cmp exit above 1 (its own operational error —
    # e.g. dest_path unreadable) would be misreported as drift instead of a
    # checker error.
    if render_template "${template_file}" | cmp -s - "${dest_path}"; then
      : # identical — clean
    else
      local -a pipe_rc=("${PIPESTATUS[@]}")
      local render_rc="${pipe_rc[0]}" cmp_rc="${pipe_rc[1]}"
      if [ "${render_rc}" -ne 0 ]; then
        echo "ERROR: failed to render ${template_file}" >&2
        had_error=true
      elif [ "${cmp_rc}" -eq 1 ]; then
        drifted+=("${unit}")
      else
        echo "ERROR: failed to compare rendered ${unit} against ${dest_path} (cmp exit ${cmp_rc})" >&2
        had_error=true
      fi
    fi
  done

  if [ "${had_error}" = "true" ]; then
    exit 1
  fi

  if [ "${#drifted[@]}" -gt 0 ]; then
    printf '%s\n' "${drifted[@]}"
  fi
  exit 0
}

if [ "${1:-}" = "--check-drift" ]; then
  check_drift
fi

# Refuse to run from a linked git worktree — this installs systemd/launchd units
# carrying absolute repo paths; they must bind the canonical checkout.
GUARD_OP="make install-runtime"
. "${REPO_ROOT}/bin/lib/assert-canonical-checkout.sh"
PYTHONPATH="${REPO_ROOT}" "${REPO_ROOT}/.venv/bin/python" -c "from lib.host_gate import require_host; require_host('make install-runtime')"

ITSUP="${ITSUP_ROOT}/.venv/bin/itsup"
STATE_FILE="${ITSUP_ROOT}/.itsup-supervision-state"
CUTOVER_STATE=""
BRINGUP_ACTIVE=false

write_cutover_state() {
  local value="$1"
  local temporary="${STATE_FILE}.tmp"
  printf '%s\n' "${value}" > "${temporary}"
  mv "${temporary}" "${STATE_FILE}"
}

capture_cutover_state() {
  local record="absent"
  local installed=false
  local registered=false

  if [ -e "${STATE_FILE}" ]; then
    if [ ! -r "${STATE_FILE}" ]; then
      record="unreadable"
    else
      record="$(cat "${STATE_FILE}")" || record="unreadable"
      case "${record}" in
        attempting|complete) ;;
        *) record="unreadable" ;;
      esac
    fi
  fi

  if [ "${PLATFORM}" = "linux" ]; then
    if [ -f "${SERVICE_DIR}/itsup-api.service" ] || [ -f "${SERVICE_DIR}/itsup-monitor.service" ]; then
      installed=true
    fi
    if [ "$(systemctl show itsup-api.service -p LoadState --value 2>/dev/null || true)" = "loaded" ] \
      || [ "$(systemctl show itsup-monitor.service -p LoadState --value 2>/dev/null || true)" = "loaded" ]; then
      registered=true
    fi
    if systemctl is-active --quiet itsup-bringup.service 2>/dev/null; then
      BRINGUP_ACTIVE=true
    fi
  else
    [ -f "${SERVICE_DIR}/ai.itsup.api.plist" ] && installed=true
    if launchctl print "gui/$(id -u "${ITSUP_USER}")/ai.itsup.api" >/dev/null 2>&1; then
      registered=true
    fi
    if launchctl print "gui/$(id -u "${ITSUP_USER}")/ai.itsup.bringup" >/dev/null 2>&1; then
      BRINGUP_ACTIVE=true
    fi
  fi

  case "${record}" in
    absent)
      if [ "${installed}" = "false" ] && [ "${registered}" = "false" ]; then
        CUTOVER_STATE="fresh"
      else
        CUTOVER_STATE="ambiguous"
      fi
      ;;
    attempting) CUTOVER_STATE="attempting" ;;
    complete) CUTOVER_STATE="complete" ;;
    unreadable) CUTOVER_STATE="unreadable" ;;
  esac
}

require_unambiguous_cutover() {
  capture_cutover_state
  case "${CUTOVER_STATE}" in
    ambiguous|unreadable)
      echo "ERROR: supervision cutover state is ${CUTOVER_STATE}; starting nothing." >&2
      echo "Recover by either running '${ITSUP} run' successfully then atomically writing complete," >&2
      echo "or by atomically writing complete when the current stopped state is intended." >&2
      exit 1
      ;;
    fresh)
      write_cutover_state attempting
      CUTOVER_STATE="attempting"
      ;;
  esac
}

supervisor_pids() {
  if [ "${PLATFORM}" = "linux" ]; then
    systemctl show itsup-api.service itsup-monitor.service -p MainPID --value 2>/dev/null \
      | awk '/^[1-9][0-9]*$/ { print }'
  else
    launchctl print "gui/$(id -u "${ITSUP_USER}")/ai.itsup.api" 2>/dev/null \
      | awk '/pid = [1-9][0-9]*/ { print $3; exit }'
  fi
}

is_supervisor_owned() {
  local pid="$1"
  supervisor_pids | grep -qx "${pid}"
}

terminate_legacy_pid() {
  local pid="$1"
  sudo kill -TERM "${pid}"
  for _ in {1..10}; do
    if ! sudo kill -0 "${pid}" 2>/dev/null; then
      return
    fi
    sleep 1
  done
  sudo kill -KILL "${pid}"
}

sweep_legacy_daemons() {
  local pattern match_pattern pid command
  for pattern in "${ITSUP_ROOT}/api/main.py" "${ITSUP_ROOT}/bin/monitor.py"; do
    match_pattern="$(printf '%s' "${pattern}" | sed 's/[][\\.^$*+?{}|()]/\\&/g')"
    while IFS= read -r pid; do
      [ -n "${pid}" ] || continue
      command="$(ps -p "${pid}" -o command=)"
      if [[ "${command}" != *"${pattern}"* ]]; then
        echo "ERROR: cannot attribute PID ${pid} to this checkout; aborting cutover." >&2
        return 1
      fi
      if is_supervisor_owned "${pid}"; then
        continue
      fi
      echo "Stopping legacy daemon PID ${pid}..."
      terminate_legacy_pid "${pid}"
    done < <(pgrep -f "${match_pattern}" || true)
  done
}

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
  fi
  echo ""
}

ensure_mutating_host_prereqs() {
  if [ "${PLATFORM}" = "linux" ]; then
    ensure_dns_fallback_linux
    ensure_nonlocal_bind_linux
  fi
  echo ""
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

ensure_nonlocal_bind_linux() {
  # AdGuard intentionally binds DNS to the configured LAN address only, but
  # Docker may recreate it before DHCP has assigned that address during boot.
  # ip_nonlocal_bind keeps that narrow bind possible without publishing DNS on
  # every host interface.
  echo "Ensuring LAN-address port binding works before DHCP..."
  capture_nonlocal_bind_state_linux
  local write_rc=0
  write_if_changed "${SYSCTL_TEMPLATE}" "${SYSCTL_DEST}" true || write_rc=$?
  if [ "${write_rc}" -eq 2 ]; then
    echo "ERROR: aborting install — failed to write ${SYSCTL_DEST}" >&2
    exit 1
  fi

  if [ "$(read_nonlocal_bind_linux)" = "1" ]; then
    echo "  net.ipv4.ip_nonlocal_bind already active"
  else
    write_nonlocal_bind_linux 1
    echo "  net.ipv4.ip_nonlocal_bind activated"
  fi
}

capture_nonlocal_bind_state_linux() {
  if [ -e "${SYSCTL_STATE_FILE}" ]; then
    return
  fi
  local file_present=0
  if [ -e "${SYSCTL_DEST}" ]; then
    if [ ! -f "${SYSCTL_DEST}" ]; then
      echo "ERROR: ${SYSCTL_DEST} exists but is not a regular file" >&2
      exit 1
    fi
    file_present=1
  fi
  local runtime_value
  runtime_value="$(read_nonlocal_bind_linux)"
  local temporary="${SYSCTL_STATE_FILE}.tmp"
  local content_temporary="${SYSCTL_STATE_CONTENT_FILE}.tmp"
  local file_mode="" file_owner="" file_group=""
  rm -f "${content_temporary}"
  if [ "${file_present}" = "1" ]; then
    file_mode="$(stat -c '%a' "${SYSCTL_DEST}")"
    file_owner="$(stat -c '%u' "${SYSCTL_DEST}")"
    file_group="$(stat -c '%g' "${SYSCTL_DEST}")"
    if ! sudo cat "${SYSCTL_DEST}" > "${content_temporary}"; then
      echo "ERROR: failed to capture original ${SYSCTL_DEST}" >&2
      rm -f "${content_temporary}"
      exit 1
    fi
  fi
  {
    printf 'file_present=%s\n' "${file_present}"
    printf 'runtime_value=%s\n' "${runtime_value}"
    if [ "${file_present}" = "1" ]; then
      printf 'file_mode=%s\n' "${file_mode}"
      printf 'file_owner=%s\n' "${file_owner}"
      printf 'file_group=%s\n' "${file_group}"
    fi
  } > "${temporary}"
  if [ "${file_present}" = "1" ]; then
    mv "${content_temporary}" "${SYSCTL_STATE_CONTENT_FILE}"
  else
    rm -f "${SYSCTL_STATE_CONTENT_FILE}"
  fi
  mv "${temporary}" "${SYSCTL_STATE_FILE}"
}

read_nonlocal_bind_linux() {
  /sbin/sysctl -n net.ipv4.ip_nonlocal_bind 2>/dev/null \
    || /usr/sbin/sysctl -n net.ipv4.ip_nonlocal_bind 2>/dev/null \
    || sysctl -n net.ipv4.ip_nonlocal_bind 2>/dev/null \
    || printf 'unknown'
}

write_nonlocal_bind_linux() {
  local value="$1"
  sudo /sbin/sysctl -w "net.ipv4.ip_nonlocal_bind=${value}" >/dev/null 2>&1 \
    || sudo /usr/sbin/sysctl -w "net.ipv4.ip_nonlocal_bind=${value}" >/dev/null 2>&1 \
    || sudo sysctl -w "net.ipv4.ip_nonlocal_bind=${value}" >/dev/null
}

# ── systemd (Linux) ────────────────────────────────────────────────────────

ensure_systemd_journal_group() {
  # The alert unit runs as the itsUP user (never root) and reads other units'
  # journals to compose an alert body; systemd-journal membership is what
  # makes that possible without privilege escalation (D3).
  if id -nG "${ITSUP_USER}" | tr ' ' '\n' | grep -qx systemd-journal; then
    return
  fi
  echo "Adding ${ITSUP_USER} to the systemd-journal group..."
  sudo usermod -aG systemd-journal "${ITSUP_USER}"
}

install_systemd_units() {
  ensure_systemd_journal_group

  local bringup_changed=false
  for unit in "${SYSTEMD_UNITS[@]}"; do
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
  if [ "${bringup_changed}" = "true" ] || [ "${BRINGUP_ACTIVE}" = "false" ]; then
    sudo systemctl restart itsup-bringup.service
    if [ "${CUTOVER_STATE}" = "attempting" ]; then
      write_cutover_state complete
      CUTOVER_STATE="complete"
    fi
  elif [ "${CUTOVER_STATE}" = "attempting" ]; then
    ITSUP_ROOT="${ITSUP_ROOT}" "${ITSUP}" run
    write_cutover_state complete
    CUTOVER_STATE="complete"
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
    "ai.itsup.api"
  )

  mkdir -p "${SERVICE_DIR}"
  local domain
  domain="gui/$(id -u "${ITSUP_USER}")"

  local bringup_changed=false
  local apply_changed=false
  local backup_changed=false
  for label in "${agents[@]}"; do
    local plist="${SERVICE_DIR}/${label}.plist"
    local template="${TEMPLATE_DIR}/${label}.plist"

    local write_rc=0
    write_if_changed "${template}" "${plist}" || write_rc=$?
    if [ "${write_rc}" -eq 2 ]; then
      echo "ERROR: aborting install — failed to write ${plist}" >&2
      exit 1
    fi
    if [ "${label}" = "ai.itsup.bringup" ] && [ "${write_rc}" -eq 0 ]; then
      bringup_changed=true
    fi
    if [ "${label}" = "ai.itsup.apply" ] && [ "${write_rc}" -eq 0 ]; then
      apply_changed=true
    fi
    if [ "${label}" = "ai.itsup.backup" ] && [ "${write_rc}" -eq 0 ]; then
      backup_changed=true
    fi
  done

  reload_launchd_agent() {
    local label="$1"
    local plist="${SERVICE_DIR}/${label}.plist"
    launchctl bootout "${domain}" "${plist}" 2>/dev/null \
      || launchctl unload "${plist}" 2>/dev/null || true
    if ! launchctl bootstrap "${domain}" "${plist}" 2>/dev/null; then
      launchctl load "${plist}"
    fi
  }

  for label in "ai.itsup.apply" "ai.itsup.backup"; do
    local plist="${SERVICE_DIR}/${label}.plist"
    local changed=false
    if [ "${label}" = "ai.itsup.apply" ]; then
      changed="${apply_changed}"
    else
      changed="${backup_changed}"
    fi
    if [ "${changed}" = "true" ] || ! launchctl print "${domain}/${label}" >/dev/null 2>&1; then
      reload_launchd_agent "${label}"
    fi
  done

  if [ "${CUTOVER_STATE}" = "attempting" ] || [ "${bringup_changed}" = "true" ] \
    || [ "${BRINGUP_ACTIVE}" = "false" ]; then
    reload_launchd_agent "ai.itsup.bringup"
  else
    echo "  ai.itsup.bringup unchanged and loaded, skipping reload"
  fi

  if [ "${CUTOVER_STATE}" = "attempting" ]; then
    local attempts=0
    while [ "${attempts}" -lt 150 ]; do
      if [ -r "${STATE_FILE}" ] && [ "$(cat "${STATE_FILE}")" = "complete" ]; then
        CUTOVER_STATE="complete"
        break
      fi
      sleep 2
      attempts=$((attempts + 1))
    done
    if [ "${CUTOVER_STATE}" != "complete" ]; then
      echo "ERROR: timed out waiting for the bringup guardian; inspect itsUP bringup logs." >&2
      exit 1
    fi
  fi

  echo "✓ ai.itsup.bringup loaded (runs at load)"
  echo "✓ ai.itsup.apply loaded (03:00 nightly apply)"
  echo "✓ ai.itsup.backup loaded (05:00 nightly backup)"
}

# ── Dispatch ───────────────────────────────────────────────────────────────

ensure_host_prereqs
require_unambiguous_cutover
sweep_legacy_daemons
ensure_mutating_host_prereqs

case "${PLATFORM}" in
  linux) install_systemd_units;;
  macos) install_launchd_agents;;
esac
