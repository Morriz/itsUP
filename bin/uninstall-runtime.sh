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

case "$(uname -s)" in
  Darwin*) PLATFORM="macos";;
  Linux*)  PLATFORM="linux";;
  *)       echo "Unsupported platform: $(uname -s)" >&2; exit 1;;
esac

if [ "${PLATFORM}" = "macos" ]; then
  SERVICE_DIR="${SERVICE_DIR:-${ITSUP_HOME}/Library/LaunchAgents}"
else
  SERVICE_DIR="${SERVICE_DIR:-/etc/systemd/system}"
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
  if [ ! -x "${ITSUP}" ]; then
    echo "⚠ ${ITSUP} not found — cannot run the CLI stack teardown."
    # No CLI, but if itsUP processes are somehow up they cannot be torn down
    # cleanly here — fail closed so the operator notices. With nothing running,
    # there is nothing to tear down, so proceed.
    if remnant_processes; then
      echo "✗ itsUP processes are running but ${ITSUP} is absent — install deps and re-run." >&2
      return 1
    fi
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
  if remnant_processes; then
    echo "✗ itsUP host process(es) survived 'itsup down --clean'." >&2
    return 1
  fi
  if remnant_containers; then
    echo "✗ itsUP container(s) survived 'itsup down --clean'." >&2
    return 1
  fi
}

# True when an itsUP-managed host process (the monitor or the API server, both
# started by `itsup run`) is still alive.
remnant_processes() {
  pgrep -f 'bin/monitor.py' >/dev/null 2>&1 || pgrep -f 'api/main.py' >/dev/null 2>&1
}

# True when any container of an itsUP compose project is still running. Asks each
# of itsUP's own compose files (the same ones `itsup down` operates on) rather
# than re-deriving the container set — `docker compose ps -q` lists running IDs.
remnant_containers() {
  command -v docker >/dev/null 2>&1 || return 1
  local files=("${ITSUP_ROOT}/proxy/docker-compose.yml" "${ITSUP_ROOT}/dns/docker-compose.yml")
  local f
  for f in "${ITSUP_ROOT}"/upstream/*/docker-compose.yml; do
    [ -f "$f" ] && files+=("$f")
  done
  for f in "${files[@]}"; do
    [ -f "$f" ] || continue
    if [ -n "$(docker compose -f "$f" ps -q 2>/dev/null)" ]; then
      return 0
    fi
  done
  return 1
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
  )
  local removed=0
  for unit in "${units[@]}"; do
    if [ -f "${SERVICE_DIR}/${unit}" ]; then
      echo "Removing ${SERVICE_DIR}/${unit}..."
      sudo rm -f "${SERVICE_DIR}/${unit}"
      removed=1
    fi
  done
  if [ "${removed}" = "1" ]; then
    echo "Reloading systemd..."
    sudo systemctl daemon-reload
  fi
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
    if command -v systemctl >/dev/null 2>&1; then
      disable_systemd_units
      assert_systemd_inactive || abort_incomplete
    fi
    teardown_stack || abort_incomplete
    if command -v systemctl >/dev/null 2>&1; then remove_systemd_units; fi
    ;;
  macos)
    bootout_launchd_agents
    teardown_stack || abort_incomplete
    remove_launchd_agents
    ;;
esac

rm -f "${ITSUP_ROOT}/.itsup-supervision-state"

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
