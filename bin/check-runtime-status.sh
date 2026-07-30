#!/usr/bin/env bash
set -euo pipefail

# Read-only runtime health summary for the container host.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ITSUP_USER="${ITSUP_USER:-${USER:-$(id -un)}}"
ITSUP_GROUP="${ITSUP_GROUP:-$(id -gn "${ITSUP_USER}")}"
ITSUP_ROOT="${ITSUP_ROOT:-${REPO_ROOT}}"
ITSUP="${ITSUP_ROOT}/.venv/bin/itsup"
PYTHON="${ITSUP_ROOT}/.venv/bin/python"
ITSUP_HOME="${HOME:-/Users/${ITSUP_USER}}"

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

warn() {
  printf 'WARN %s\n' "$*" >&2
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

render_template() {
  local template_file="$1"
  sed \
    -e "s|{{USER}}|${ITSUP_USER}|g" \
    -e "s|{{GROUP}}|${ITSUP_GROUP}|g" \
    -e "s|{{ROOT}}|${ITSUP_ROOT}|g" \
    -e "s|{{HOME}}|${ITSUP_HOME}|g" \
    "${template_file}"
}

check_host_gate() {
  if [ ! -x "${PYTHON}" ]; then
    fail "missing Python venv: ${PYTHON}"
    return
  fi
  if PYTHONPATH="${ITSUP_ROOT}" "${PYTHON}" -c "from lib.host_gate import require_host; require_host('make status')" >/dev/null 2>&1; then
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

check_alert_command() {
  if [ ! -x "${PYTHON}" ]; then
    fail "missing Python venv: ${PYTHON}"
    return
  fi

  local result
  if ! result="$(PYTHONPATH="${ITSUP_ROOT}" "${PYTHON}" - <<'PY'
from lib.alerting import _resolve_command_template
from lib.data import load_itsup_config

template = _resolve_command_template(load_itsup_config())
if template is None:
    print("missing")
else:
    print(f"configured:{template[0]}")
PY
  )"; then
    fail "alert.command configuration check failed: ${result//$'\n'/, }"
    return
  fi

  if [ "${result}" = "missing" ]; then
    warn "alert.command is not configured; failure alerts will be suppressed"
  elif [[ "${result}" == configured:* ]]; then
    ok "alert.command is configured (${result#configured:})"
  else
    fail "alert.command configuration check returned unexpected result: ${result//$'\n'/, }"
  fi
}

check_unit_drift() {
  case "$(uname -s)" in
    Linux)
      local drift
      if ! drift="$(ITSUP_ROOT="${ITSUP_ROOT}" "${REPO_ROOT}/bin/install-bringup.sh" --check-drift)"; then
        fail "systemd unit drift check failed"
        return
      fi
      if [ -n "${drift}" ]; then
        fail "installed systemd units drifted: ${drift//$'\n'/, }"
      else
        ok "installed systemd units match templates"
      fi
      ;;
    Darwin*)
      local service_dir="${SERVICE_DIR:-${ITSUP_HOME}/Library/LaunchAgents}"
      local label template dest
      local -a drifted=()
      for label in ai.itsup.bringup ai.itsup.apply ai.itsup.backup ai.itsup.api; do
        template="${REPO_ROOT}/samples/launchd/${label}.plist"
        dest="${service_dir}/${label}.plist"
        if [ ! -r "${template}" ]; then
          fail "launchd template not readable: ${template}"
          continue
        fi
        if [ ! -f "${dest}" ]; then
          drifted+=("${label}")
          continue
        fi
        if ! render_template "${template}" | cmp -s - "${dest}"; then
          drifted+=("${label}")
        fi
      done
      if [ "${#drifted[@]}" -gt 0 ]; then
        fail "installed launchd agents drifted: ${drifted[*]}"
      else
        ok "installed launchd agents match templates"
      fi
      ;;
    *)
      fail "unsupported platform: $(uname -s)"
      ;;
  esac
}

check_systemd() {
  if [ "$(uname -s)" != "Linux" ]; then
    skip "systemd status check is Linux-only"
    return
  fi
  require_cmd systemctl || return

  local failed_units
  if ! failed_units="$(systemctl --failed --no-legend --no-pager 2>/dev/null)"; then
    fail "systemd failed-unit query failed"
    return
  fi
  if [ -n "${failed_units}" ]; then
    fail "systemd has failed units: ${failed_units//$'\n'/, }"
  else
    ok "systemd has no failed units"
  fi

  local unit
  for unit in itsup-bringup.service itsup-api.service itsup-monitor.service itsup-apply.timer itsup-backup.timer pi-healthcheck.timer; do
    if systemctl is-active --quiet "${unit}"; then
      ok "${unit} is active"
    else
      fail "${unit} is not active"
    fi
  done
}

check_launchd() {
  if [[ "$(uname -s)" != Darwin* ]]; then
    return
  fi
  require_cmd launchctl || return

  local label details
  for label in ai.itsup.bringup ai.itsup.apply ai.itsup.backup ai.itsup.api; do
    if ! details="$(launchctl print "gui/$(id -u "${ITSUP_USER}")/${label}" 2>/dev/null)"; then
      fail "${label} is not registered with launchd"
      continue
    fi
    ok "${label} is registered with launchd"

    # Apply and backup are calendar jobs; only resident daemons should be running.
    case "${label}" in
      ai.itsup.bringup|ai.itsup.api)
        if grep -Eq 'state = running|pid = [0-9]+' <<<"${details}"; then
          ok "${label} is running"
        else
          fail "${label} is not running"
        fi
        ;;
    esac
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

  local unhealthy restarting bad
  if ! unhealthy="$(docker ps --filter health=unhealthy --format '{{.Names}} {{.Status}}')"; then
    fail "unhealthy-container query failed"
    return
  fi
  if ! restarting="$(docker ps --filter status=restarting --format '{{.Names}} {{.Status}}')"; then
    fail "restarting-container query failed"
    return
  fi
  bad="$(printf '%s\n%s\n' "${unhealthy}" "${restarting}" | awk 'NF && !seen[$0]++')"
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

  local sysctl_bin value sysctl_file sysctl_template
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

  sysctl_file="/etc/sysctl.d/99-itsup-nonlocal-bind.conf"
  sysctl_template="${REPO_ROOT}/samples/sysctl/99-itsup-nonlocal-bind.conf"
  if [ ! -r "${sysctl_file}" ]; then
    fail "persistent ip_nonlocal_bind sysctl file is missing: ${sysctl_file}"
  elif cmp -s "${sysctl_template}" "${sysctl_file}"; then
    ok "persistent ip_nonlocal_bind sysctl file matches template"
  else
    fail "persistent ip_nonlocal_bind sysctl file drifted: ${sysctl_file}"
  fi
}

check_adguard_dns() {
  require_cmd docker || return

  local address adguard ports
  if ! address="$(host_ip)"; then
    fail "SSH_HOST lookup failed"
    return
  fi
  if [ -z "${address}" ]; then
    fail "SSH_HOST is not configured"
    return
  fi

  if ! adguard="$(find_container '^adguard-.*adguard.*')"; then
    fail "AdGuard container query failed"
    return
  fi
  if [ -z "${adguard}" ]; then
    fail "AdGuard container is not running"
    return
  fi
  ok "AdGuard container is running (${adguard})"

  if ! ports="$(docker inspect "${adguard}" --format '{{range $port, $bindings := .NetworkSettings.Ports}}{{range $bindings}}{{println $port .HostIp .HostPort}}{{end}}{{end}}')"; then
    fail "AdGuard published-port query failed"
    return
  fi
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
  if ! traefik="$(find_container 'traefik')"; then
    fail "Traefik container query failed"
    return
  fi
  if [ -z "${traefik}" ]; then
    fail "Traefik container is not running"
    return
  fi
  ok "Traefik container is running (${traefik})"

  if ! health="$(docker inspect "${traefik}" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}')"; then
    fail "Traefik health query failed"
    return
  fi
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

check_openvpn() {
  require_cmd docker || return

  if [ ! -f "${ITSUP_ROOT}/projects/vpn/docker-compose.yml" ]; then
    skip "OpenVPN project is not configured"
    return
  fi

  local address openvpn ports health
  if ! address="$(host_ip)"; then
    fail "SSH_HOST lookup failed"
    return
  fi
  if [ -z "${address}" ]; then
    fail "SSH_HOST is not configured"
    return
  fi

  if ! openvpn="$(find_container '^vpn-.*openvpn.*')"; then
    fail "OpenVPN container query failed"
    return
  fi
  if [ -z "${openvpn}" ]; then
    fail "OpenVPN container is not running"
    return
  fi
  ok "OpenVPN container is running (${openvpn})"

  if ! health="$(docker inspect "${openvpn}" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}')"; then
    fail "OpenVPN health query failed"
    return
  fi
  if [ "${health}" = "healthy" ]; then
    ok "OpenVPN container health is healthy"
  elif [ "${health}" = "none" ]; then
    skip "OpenVPN container has no healthcheck"
  else
    fail "OpenVPN container health is ${health}"
  fi

  if ! ports="$(docker inspect "${openvpn}" --format '{{range $port, $bindings := .NetworkSettings.Ports}}{{range $bindings}}{{println $port .HostIp .HostPort}}{{end}}{{end}}')"; then
    fail "OpenVPN published-port query failed"
    return
  fi
  if grep -qx "1194/udp ${address} 1194" <<<"${ports}"; then
    ok "OpenVPN UDP is bound directly to ${address}:1194"
  else
    fail "OpenVPN UDP is not bound directly to ${address}:1194"
    printf '%s\n' "${ports}" >&2
  fi
}

cd "${REPO_ROOT}"

check_host_gate
check_config
check_alert_command
check_unit_drift
check_systemd
check_launchd
check_docker
check_nonlocal_bind
check_adguard_dns
check_traefik
check_openvpn

if [ "${failures}" -gt 0 ]; then
  printf 'Runtime status failed: %d issue(s)\n' "${failures}" >&2
  exit 1
fi

printf 'Runtime status OK\n'
