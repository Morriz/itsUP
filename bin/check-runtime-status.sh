#!/usr/bin/env bash
set -euo pipefail

# Read-only runtime health summary for the container host.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ITSUP="${REPO_ROOT}/.venv/bin/itsup"
PYTHON="${REPO_ROOT}/.venv/bin/python"

failures=0

ok() {
  printf 'OK %s\n' "$*"
}

fail() {
  failures=$((failures + 1))
  printf 'FAIL %s\n' "$*" >&2
}

skip() {
  printf 'SKIP %s\n' "$*"
}

have() {
  command -v "$1" >/dev/null 2>&1
}

require_cmd() {
  if ! have "$1"; then
    fail "missing command: $1"
    return 1
  fi
}

find_cmd() {
  local name="$1"
  shift
  command -v "${name}" 2>/dev/null || {
    local candidate
    for candidate in "$@"; do
      if [ -x "${candidate}" ]; then
        printf '%s\n' "${candidate}"
        return 0
      fi
    done
    return 1
  }
}

host_ip() {
  "${PYTHON}" - <<'PY'
from lib.host_gate import configured_host

print(configured_host() or "")
PY
}

find_container() {
  local pattern="$1"
  docker ps --format '{{.Names}}' | awk -v pattern="${pattern}" '$0 ~ pattern { print; exit }'
}

check_host_gate() {
  if [ ! -x "${PYTHON}" ]; then
    fail "missing Python venv: ${PYTHON}"
    return
  fi
  if PYTHONPATH="${REPO_ROOT}" "${PYTHON}" -c "from lib.host_gate import require_host; require_host('make status')" >/dev/null 2>&1; then
    ok "host identity matches SSH_HOST"
  else
    fail "host identity does not match SSH_HOST"
  fi
}

check_config() {
  if [ ! -x "${ITSUP}" ]; then
    fail "missing itsup CLI: ${ITSUP}"
    return
  fi
  if "${ITSUP}" validate >/dev/null; then
    ok "project configuration validates"
  else
    fail "project configuration validation failed"
  fi
}

check_unit_drift() {
  if [ "$(uname -s)" != "Linux" ]; then
    skip "systemd unit drift check is Linux-only"
    return
  fi

  local drift
  if ! drift="$("${REPO_ROOT}/bin/install-bringup.sh" --check-drift)"; then
    fail "systemd unit drift check failed"
    return
  fi
  if [ -n "${drift}" ]; then
    fail "installed systemd units drifted: ${drift//$'\n'/, }"
  else
    ok "installed systemd units match templates"
  fi
}

check_systemd() {
  if [ "$(uname -s)" != "Linux" ]; then
    skip "systemd status check is Linux-only"
    return
  fi
  require_cmd systemctl || return

  local failed_units
  failed_units="$(systemctl --failed --no-legend --no-pager 2>/dev/null || true)"
  if [ -n "${failed_units}" ]; then
    fail "systemd has failed units: ${failed_units//$'\n'/, }"
  else
    ok "systemd has no failed units"
  fi

  local unit
  for unit in itsup-bringup.service itsup-apply.timer itsup-backup.timer pi-healthcheck.timer; do
    if systemctl is-active --quiet "${unit}"; then
      ok "${unit} is active"
    else
      fail "${unit} is not active"
    fi
  done
}

check_docker() {
  require_cmd docker || return

  if docker ps >/dev/null 2>&1; then
    ok "docker is reachable"
  else
    fail "docker is not reachable"
    return
  fi

  local bad
  bad="$(docker ps --filter health=unhealthy --filter status=restarting --format '{{.Names}} {{.Status}}' || true)"
  if [ -n "${bad}" ]; then
    fail "containers unhealthy or restarting: ${bad//$'\n'/, }"
  else
    ok "no unhealthy or restarting containers"
  fi
}

check_nonlocal_bind() {
  if [ "$(uname -s)" != "Linux" ]; then
    skip "ip_nonlocal_bind check is Linux-only"
    return
  fi

  local sysctl_bin value
  if ! sysctl_bin="$(find_cmd sysctl /sbin/sysctl /usr/sbin/sysctl)"; then
    fail "missing command: sysctl"
    return
  fi

  value="$("${sysctl_bin}" -n net.ipv4.ip_nonlocal_bind 2>/dev/null || true)"
  if [ "${value}" = "1" ]; then
    ok "net.ipv4.ip_nonlocal_bind is active"
  else
    fail "net.ipv4.ip_nonlocal_bind is ${value:-unreadable}"
  fi
}

check_adguard_dns() {
  require_cmd docker || return

  local address adguard ports
  address="$(host_ip)"
  if [ -z "${address}" ]; then
    fail "SSH_HOST is not configured"
    return
  fi

  adguard="$(find_container '^adguard-.*adguard.*')"
  if [ -z "${adguard}" ]; then
    fail "AdGuard container is not running"
    return
  fi
  ok "AdGuard container is running (${adguard})"

  ports="$(docker inspect "${adguard}" --format '{{range $port, $bindings := .NetworkSettings.Ports}}{{range $bindings}}{{println $port .HostIp .HostPort}}{{end}}{{end}}')"
  if grep -qx "53/tcp ${address} 53" <<<"${ports}" && grep -qx "53/udp ${address} 53" <<<"${ports}"; then
    ok "AdGuard DNS is bound to ${address}:53"
  else
    fail "AdGuard DNS is not bound to ${address}:53"
    printf '%s\n' "${ports}" >&2
  fi

  if have dig; then
    if dig @"${address}" google.com +time=2 +tries=1 +short | grep -Eq '^[0-9a-fA-F:.]+$'; then
      ok "AdGuard resolves external DNS"
    else
      fail "AdGuard did not resolve external DNS"
    fi
  elif have nc; then
    if nc -z -w 2 "${address}" 53; then
      ok "AdGuard DNS port accepts TCP connections"
    else
      fail "AdGuard DNS port does not accept TCP connections"
    fi
  else
    skip "dig/nc unavailable; DNS query not checked"
  fi
}

check_traefik() {
  require_cmd docker || return

  local traefik health
  traefik="$(find_container 'traefik')"
  if [ -z "${traefik}" ]; then
    fail "Traefik container is not running"
    return
  fi
  ok "Traefik container is running (${traefik})"

  health="$(docker inspect "${traefik}" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}')"
  if [ "${health}" = "healthy" ]; then
    ok "Traefik container health is healthy"
  else
    fail "Traefik container health is ${health}"
  fi

  if docker exec "${traefik}" wget -q -O /dev/null -T 5 http://127.0.0.1:8082/ping; then
    ok "Traefik ping endpoint answers"
  else
    fail "Traefik ping endpoint does not answer"
  fi
}

cd "${REPO_ROOT}"

check_host_gate
check_config
check_unit_drift
check_systemd
check_docker
check_nonlocal_bind
check_adguard_dns
check_traefik

if [ "${failures}" -gt 0 ]; then
  printf 'Runtime status failed: %d issue(s)\n' "${failures}" >&2
  exit 1
fi

printf 'Runtime status OK\n'
