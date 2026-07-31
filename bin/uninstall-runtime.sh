#!/usr/bin/env bash
set -euo pipefail

# Decommissions the itsUP runtime on a host: stops everything this stack brought
# up and removes the host integration that keeps re-bringing it up. The inverse of
# bin/install-bringup.sh. Cross-platform (systemd on Linux, launchd on macOS),
# idempotent, and scoped to itsUP-managed resources only.
#
# Order matters. Resurrection sources (the apply/backup timers and pi-healthcheck,
# which can auto-recover or even reboot the host) are disabled FIRST so nothing
# restarts the stack mid-teardown. Then the stack is torn down through the CLI's
# own primitives — `itsup down --clean` (which stops the monitor and API host
# processes and downs+removes every itsUP container) and `itsup monitor
# clear-iptables` — so no orphaned process, container, or firewall rule survives.
# Reimplementing the teardown here would inevitably miss one of those. Then the
# unit/agent files are removed.
#
# Deliberately NOT reversed (printed at the end): Docker volumes / project data,
# host DNS fallback, and shared system packages.
# Decommissioning the runtime is not destroying data or host policy.
#
# Env overrides (match install-bringup.sh): ITSUP_USER, ITSUP_ROOT, SERVICE_DIR.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Refuse to run from a linked git worktree — runtime teardown operates on the
# canonical checkout's stacks/units, never a transient worktree copy.
GUARD_OP="make uninstall-runtime"
. "${REPO_ROOT}/bin/lib/assert-canonical-checkout.sh"

ITSUP_USER="${ITSUP_USER:-${USER:-$(id -un)}}"
ITSUP_ROOT="${ITSUP_ROOT:-${REPO_ROOT}}"
ITSUP_HOME="${HOME:-/Users/${ITSUP_USER}}"
ITSUP="${ITSUP_ROOT}/.venv/bin/itsup"
PYTHON="${ITSUP_ROOT}/.venv/bin/python"

case "$(uname -s)" in
  Darwin*) PLATFORM="macos";;
  Linux*)  PLATFORM="linux";;
  *)       echo "Unsupported platform: $(uname -s)" >&2; exit 1;;
esac

if [ "${PLATFORM}" = "macos" ]; then
  SERVICE_DIR="${SERVICE_DIR:-${ITSUP_HOME}/Library/LaunchAgents}"
else
  SERVICE_DIR="${SERVICE_DIR:-/etc/systemd/system}"
  SYSCTL_DEST="${SYSCTL_DEST:-/etc/sysctl.d/99-itsup-nonlocal-bind.conf}"
  SYSCTL_STATE_FILE="${ITSUP_ROOT}/.itsup-nonlocal-bind-state"
  SYSCTL_STATE_CONTENT_FILE="${ITSUP_ROOT}/.itsup-nonlocal-bind-state.content"
  . "${REPO_ROOT}/bin/lib/nonlocal-bind-state.sh"
fi

# ── Step 1: disable the resurrection sources first ─────────────────────────

disable_systemd_units() {
  # --now disables AND stops. Stopping itsup-bringup.service fires its
  # ExecStop=`itsup down`; the explicit `itsup down --clean` below then guarantees
  # full removal. Order: kill the auto-restart/reboot sources before the stack.
  local timers=(
    "pi-healthcheck.timer"
    "itsup-apply.timer"
    "itsup-backup.timer"
    "itsup-bringup.service"
  )
  for unit in "${timers[@]}"; do
    if [ -f "${SERVICE_DIR}/${unit}" ]; then
      echo "Disabling ${unit}..."
      sudo systemctl disable --now "${unit}" 2>/dev/null || true
    fi
  done
  # Disabling a timer does not stop the oneshot service it already launched. Stop
  # any in-flight apply/backup/healthcheck run so it cannot keep mutating the
  # stack (or reboot the host) while teardown proceeds.
  local services=(
    "itsup-apply.service"
    "itsup-backup.service"
    "pi-healthcheck.service"
    "itsup-api.service"
    "itsup-monitor.service"
  )
  for unit in "${services[@]}"; do
    if [ -f "${SERVICE_DIR}/${unit}" ]; then
      echo "Stopping ${unit}..."
      sudo systemctl stop "${unit}" 2>/dev/null || true
    fi
  done
}

# Authoritative fail-closed gate for the disable/stop step above: the individual
# disable/stop attempts are best-effort, so a swallowed failure is caught here by
# checking the actual end state. Returns non-zero if any itsUP unit is still
# active and could keep mutating the host during teardown.
assert_systemd_inactive() {
  local units=(
    "itsup-bringup.service"
    "itsup-apply.service" "itsup-apply.timer"
    "itsup-backup.service" "itsup-backup.timer"
    "pi-healthcheck.service" "pi-healthcheck.timer"
    "itsup-api.service"
    "itsup-monitor.service"
  )
  local active=0 unit
  for unit in "${units[@]}"; do
    if systemctl is-active --quiet "${unit}" 2>/dev/null; then
      echo "✗ ${unit} is still active after disable/stop." >&2
      active=1
    fi
  done
  return "${active}"
}

bootout_launchd_agents() {
  local domain
  domain="gui/$(id -u "${ITSUP_USER}")"
  local agents=("ai.itsup.apply" "ai.itsup.backup" "ai.itsup.bringup" "ai.itsup.api")
  for label in "${agents[@]}"; do
    local plist="${SERVICE_DIR}/${label}.plist"
    if [ -f "${plist}" ]; then
      # Booting out the bringup guardian fires its TERM trap -> graceful `itsup down`.
      echo "Booting out ${label}..."
      launchctl bootout "${domain}" "${plist}" 2>/dev/null \
        || launchctl unload "${plist}" 2>/dev/null || true
    fi
  done
}

# ── Step 2: tear the running stack down via the CLI's own primitives ───────

# Returns non-zero if the stack could not be fully torn down — the caller must
# then leave host integration in place rather than claim a clean decommission.
teardown_stack() {
  local identity_status
  set +e
  host_identity_matches
  identity_status=$?
  set -e
  case "${identity_status}" in
    0) ;;
    1)
      teardown_local_runtime
      return
      ;;
    *)
      echo "✗ Cannot verify whether this machine is the configured container host." >&2
      return 1
      ;;
  esac

  if [ ! -x "${ITSUP}" ]; then
    echo "⚠ ${ITSUP} not found — cannot run the CLI stack teardown."
    # No CLI, but if itsUP processes are somehow up they cannot be torn down
    # cleanly here — fail closed so the operator notices. With nothing running,
    # there is nothing to tear down, so proceed.
    local process_status
    set +e
    remnant_processes
    process_status=$?
    set -e
    case "${process_status}" in
      0)
        echo "✗ itsUP processes are running but ${ITSUP} is absent — install deps and re-run." >&2
        return 1
        ;;
      1) return 0 ;;
      *) return 1 ;;
    esac
    return 0
  fi
  echo "Stopping the full itsUP stack (itsup down --clean)..."
  if ! ( cd "${ITSUP_ROOT}" && ITSUP_ROOT="${ITSUP_ROOT}" "${ITSUP}" down --clean ); then
    echo "✗ 'itsup down --clean' failed — the stack may be partially up." >&2
    return 1
  fi
  if [ "${PLATFORM}" = "linux" ]; then
    echo "Flushing the monitor's iptables rules (itsup monitor clear-iptables)..."
    if ! ( cd "${ITSUP_ROOT}" && ITSUP_ROOT="${ITSUP_ROOT}" "${ITSUP}" monitor clear-iptables ); then
      echo "✗ 'itsup monitor clear-iptables' failed — monitor firewall rules may remain." >&2
      return 1
    fi
  fi
  # `itsup down` is documented to keep going past individual container/process stop
  # failures, so a zero exit is not proof. Verify the actual end state.
  assert_no_remnant_processes "survived 'itsup down --clean'" || return 1
  assert_no_remnant_containers "survived 'itsup down --clean'" || return 1
}

host_identity_matches() {
  if [ ! -x "${PYTHON}" ]; then
    echo "✗ ${PYTHON} not found — cannot verify host identity." >&2
    return 2
  fi

  local output status
  set +e
  output="$(PYTHONPATH="${REPO_ROOT}" "${PYTHON}" - <<'PY' 2>&1
from lib.host_gate import configured_host, detect_lan_ip

try:
    configured = configured_host()
    detected = detect_lan_ip()
except Exception as exc:  # pylint: disable=broad-exception-caught
    print(f"host identity lookup failed: {exc}")
    raise SystemExit(2)

if configured is None:
    print("configured SSH_HOST is unset")
    raise SystemExit(2)
if detected is None:
    print("detected LAN IP is unavailable")
    raise SystemExit(2)

raise SystemExit(0 if configured == detected else 1)
PY
)"
  status=$?
  set -e

  if [ "${status}" -gt 1 ] && [ -n "${output}" ]; then
    echo "✗ ${output}" >&2
  fi
  return "${status}"
}

teardown_local_runtime() {
  echo "This machine is not the configured container host; skipping host-only 'itsup down --clean'."
  echo "Tearing down local itsUP remnants directly..."
  local process_status container_status
  set +e
  remnant_processes
  process_status=$?
  set -e
  case "${process_status}" in
    0) terminate_remnant_processes || return 1 ;;
    1) ;;
    *) return 1 ;;
  esac

  set +e
  remnant_containers
  container_status=$?
  set -e
  case "${container_status}" in
    0) teardown_local_compose || return 1 ;;
    1) ;;
    *) return 1 ;;
  esac

  assert_no_remnant_processes "survived local teardown" || return 1
  assert_no_remnant_containers "survived local teardown" || return 1
}

assert_no_remnant_processes() {
  local description="$1"
  local process_status
  set +e
  remnant_processes
  process_status=$?
  set -e
  case "${process_status}" in
    0)
      echo "✗ itsUP host process(es) ${description}." >&2
      return 1
      ;;
    1) return 0 ;;
    *) return 1 ;;
  esac
}

assert_no_remnant_containers() {
  local description="$1"
  local container_status
  set +e
  remnant_containers
  container_status=$?
  set -e
  case "${container_status}" in
    0)
      echo "✗ itsUP container(s) ${description}." >&2
      return 1
      ;;
    1) return 0 ;;
    *) return 1 ;;
  esac
}

# True when an itsUP-managed host process (the monitor or the API server, both
# started by `itsup run`) is still alive.
remnant_processes() {
  local pattern match_pattern status
  for pattern in "${ITSUP_ROOT}/bin/monitor.py" "${ITSUP_ROOT}/api/main.py"; do
    match_pattern="$(escape_pgrep_pattern "${pattern}")"
    set +e
    pgrep -f "${match_pattern}" >/dev/null
    status=$?
    set -e
    case "${status}" in
      0) return 0 ;;
      1) ;;
      *)
        echo "✗ Failed to inspect local itsUP processes for ${pattern}." >&2
        return 2
        ;;
    esac
  done
  return 1
}

escape_pgrep_pattern() {
  printf '%s' "$1" | sed 's/[][\\.^$*+?{}|()]/\\&/g'
}

terminate_remnant_processes() {
  local pattern match_pattern pid pids status
  for pattern in "${ITSUP_ROOT}/bin/monitor.py" "${ITSUP_ROOT}/api/main.py"; do
    match_pattern="$(escape_pgrep_pattern "${pattern}")"
    set +e
    pids="$(pgrep -f "${match_pattern}")"
    status=$?
    set -e
    case "${status}" in
      0) ;;
      1) continue ;;
      *)
        echo "✗ Failed to inspect local itsUP processes for ${pattern}." >&2
        return 1
        ;;
    esac
    while IFS= read -r pid; do
      [ -n "${pid}" ] || continue
      echo "Stopping local itsUP process PID ${pid}..."
      kill -TERM "${pid}" 2>/dev/null || sudo kill -TERM "${pid}" || return 1
      wait_for_pid_exit "${pid}" || {
        echo "Force-stopping local itsUP process PID ${pid}..."
        kill -KILL "${pid}" 2>/dev/null || sudo kill -KILL "${pid}" || return 1
      }
    done <<< "${pids}"
  done
}

wait_for_pid_exit() {
  local pid="$1"
  for _ in {1..10}; do
    if ! kill -0 "${pid}" 2>/dev/null; then
      return 0
    fi
    sleep 1
  done
  return 1
}

compose_files() {
  local f
  printf '%s\n' "${ITSUP_ROOT}/proxy/docker-compose.yml" "${ITSUP_ROOT}/dns/docker-compose.yml"
  for f in "${ITSUP_ROOT}"/upstream/*/docker-compose.yml; do
    [ -f "${f}" ] && printf '%s\n' "${f}"
  done
}

teardown_local_compose() {
  command -v docker >/dev/null 2>&1 || {
    echo "✗ Docker is unavailable and local itsUP containers are still running." >&2
    return 1
  }

  local f ids
  while IFS= read -r f; do
    [ -f "${f}" ] || continue
    ids="$(compose_file_running_container_ids "${f}")"
    if [ -n "${ids}" ]; then
      echo "Stopping local containers from ${f}..."
      docker stop ${ids} >/dev/null || return 1
      docker rm -f ${ids} >/dev/null || return 1
    fi
  done < <(compose_files)
}

# True when any container from this checkout's generated compose files is still
# running. Uses Docker's exact config_files label so a same-named compose project
# from another checkout is not treated as an itsUP remnant.
remnant_containers() {
  command -v docker >/dev/null 2>&1 || {
    echo "✗ Docker is unavailable; cannot verify local itsUP containers." >&2
    return 2
  }
  local f ids status
  while IFS= read -r f; do
    [ -f "${f}" ] || continue
    set +e
    ids="$(compose_file_running_container_ids "${f}" 2>&1)"
    status=$?
    set -e
    if [ "${status}" -ne 0 ]; then
      echo "✗ Failed to inspect Docker containers for ${f}: ${ids}" >&2
      return 2
    fi
    if [ -n "${ids}" ]; then
      return 0
    fi
  done < <(compose_files)
  return 1
}

compose_file_running_container_ids() {
  docker ps -q --filter "label=com.docker.compose.project.config_files=$1"
}

# ── Step 3: remove the unit / agent files ──────────────────────────────────

remove_systemd_units() {
  local units=(
    "itsup-bringup.service"
    "itsup-apply.service" "itsup-apply.timer"
    "itsup-backup.service" "itsup-backup.timer"
    "pi-healthcheck.service" "pi-healthcheck.timer"
    "itsup-api.service"
    "itsup-monitor.service"
    "itsup-alert@.service"
  )
  local removed=0
  for unit in "${units[@]}"; do
    if [ -f "${SERVICE_DIR}/${unit}" ]; then
      echo "Removing ${SERVICE_DIR}/${unit}..."
      sudo rm -f "${SERVICE_DIR}/${unit}"
      removed=1
    fi
  done
  if [ -f "/etc/logrotate.d/itsup" ]; then
    echo "Removing /etc/logrotate.d/itsup..."
    sudo rm -f "/etc/logrotate.d/itsup"
  fi
  if [ "${removed}" = "1" ]; then
    echo "Reloading systemd..."
    sudo systemctl daemon-reload
  fi
}

restore_nonlocal_bind_linux() {
  if [ ! -e "${SYSCTL_STATE_FILE}" ] && [ ! -L "${SYSCTL_STATE_FILE}" ]; then
    echo "No ip_nonlocal_bind state file found; leaving host sysctl policy unchanged."
    return
  fi

  validate_nonlocal_bind_state_linux

  local file_present runtime_value
  file_present="$(awk -F= '$1 == "file_present" { print $2 }' "${SYSCTL_STATE_FILE}")"
  runtime_value="$(awk -F= '$1 == "runtime_value" { print $2 }' "${SYSCTL_STATE_FILE}")"

  case "${file_present}" in
    0)
      if [ -e "${SYSCTL_DEST}" ]; then
        echo "Removing ${SYSCTL_DEST}..."
        sudo rm -f "${SYSCTL_DEST}"
      fi
      ;;
    1)
      echo "Restoring ${SYSCTL_DEST}..."
      local temporary="${SYSCTL_DEST}.tmp.$$"
      local file_mode file_owner file_group
      file_mode="$(awk -F= '$1 == "file_mode" { print $2 }' "${SYSCTL_STATE_FILE}")"
      file_owner="$(awk -F= '$1 == "file_owner" { print $2 }' "${SYSCTL_STATE_FILE}")"
      file_group="$(awk -F= '$1 == "file_group" { print $2 }' "${SYSCTL_STATE_FILE}")"
      sudo install -m "${file_mode}" "${SYSCTL_STATE_CONTENT_FILE}" "${temporary}"
      sudo chown "${file_owner}:${file_group}" "${temporary}"
      sudo mv "${temporary}" "${SYSCTL_DEST}"
      ;;
  esac

  echo "Restoring net.ipv4.ip_nonlocal_bind=${runtime_value}..."
  write_nonlocal_bind_linux "${runtime_value}"
}

write_nonlocal_bind_linux() {
  local value="$1"
  sudo /sbin/sysctl -w "net.ipv4.ip_nonlocal_bind=${value}" >/dev/null 2>&1 \
    || sudo /usr/sbin/sysctl -w "net.ipv4.ip_nonlocal_bind=${value}" >/dev/null 2>&1 \
    || sudo sysctl -w "net.ipv4.ip_nonlocal_bind=${value}" >/dev/null
}

remove_launchd_agents() {
  local agents=("ai.itsup.bringup" "ai.itsup.apply" "ai.itsup.backup" "ai.itsup.api")
  for label in "${agents[@]}"; do
    local plist="${SERVICE_DIR}/${label}.plist"
    if [ -f "${plist}" ]; then
      echo "Removing ${plist}..."
      rm -f "${plist}"
    fi
  done
}

# ── Dispatch ───────────────────────────────────────────────────────────────

echo "🛑 Decommissioning the itsUP runtime..."
echo ""

# Tear the stack down BEFORE removing host integration. If teardown fails, the
# units stay in place so the operator can re-run rather than be left with a
# half-decommissioned host that still claims success.
abort_incomplete() {
  echo "" >&2
  echo "✗ Runtime teardown incomplete — host integration left in place. Fix the" >&2
  echo "  cause above and re-run 'make uninstall-runtime'." >&2
  exit 1
}

case "${PLATFORM}" in
  linux)
    validate_nonlocal_bind_state_linux || abort_incomplete
    if command -v systemctl >/dev/null 2>&1; then
      disable_systemd_units
      assert_systemd_inactive || abort_incomplete
    fi
    teardown_stack || abort_incomplete
    if command -v systemctl >/dev/null 2>&1; then remove_systemd_units; fi
    restore_nonlocal_bind_linux
    ;;
  macos)
    bootout_launchd_agents
    teardown_stack || abort_incomplete
    remove_launchd_agents
    ;;
esac

rm -f "${ITSUP_ROOT}/.itsup-supervision-state"
rm -f "${ITSUP_ROOT}/.itsup-nonlocal-bind-state"
rm -f "${ITSUP_ROOT}/.itsup-nonlocal-bind-state.content"

echo ""
echo "✅ itsUP runtime decommissioned."
echo ""
echo "Left in place by design (remove manually only if you truly intend to):"
echo "  • Docker volumes / project data — acme certs, CrowdSec state, upstream data"
echo "  • Shared system packages — docker, sops, age, sops-diff"
echo "  • Repo-local .venv and git hooks (developer layer — 'rm -rf .venv' to drop)"
if [ "${PLATFORM}" = "linux" ]; then
  echo "  • Host DNS fallback (resolved.conf)"
fi
echo ""
