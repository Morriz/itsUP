#!/usr/bin/env bash
set -euo pipefail

# Wait for the configured container host to answer SSH, then run its live status
# check there. This script never reboots the host; the reboot remains an
# explicit operator action.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON="${REPO_ROOT}/.venv/bin/python"

host=""
user="${ITSUP_SSH_USER:-${USER:-}}"
remote_root="~/srv"
timeout=300
interval=5

usage() {
  cat <<'EOF'
Usage: bin/wait-for-runtime-status.sh [--host <host>] [--user <user>] [--root <path>] [--timeout <seconds>] [--interval <seconds>]

Wait for SSH to become reachable, then run `make status` in the remote itsUP
checkout. If --host is omitted, SSH_HOST is read from the local itsUP config.
EOF
}

positive_int() {
  [[ "$1" =~ ^[1-9][0-9]*$ ]]
}

configured_host() {
  if [ ! -x "${PYTHON}" ]; then
    return 1
  fi
  PYTHONPATH="${REPO_ROOT}" "${PYTHON}" - <<'PY'
from lib.host_gate import configured_host

print(configured_host() or "")
PY
}

remote_cd_target() {
  if [[ "${remote_root}" =~ ^~(/[A-Za-z0-9._-]+)+$ ]]; then
    printf '%s\n' "${remote_root}"
  else
    printf '%q\n' "${remote_root}"
  fi
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --host)
      host="${2:-}"
      shift 2
      ;;
    --user)
      user="${2:-}"
      shift 2
      ;;
    --root)
      remote_root="${2:-}"
      shift 2
      ;;
    --timeout)
      timeout="${2:-}"
      shift 2
      ;;
    --interval)
      interval="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ -z "${host}" ]; then
  host="$(configured_host || true)"
fi
if [ -z "${host}" ]; then
  printf 'No host provided and SSH_HOST could not be read from local config.\n' >&2
  exit 2
fi
if [ -z "${user}" ]; then
  printf 'No user provided; pass --user or set ITSUP_SSH_USER.\n' >&2
  exit 2
fi
if ! positive_int "${timeout}"; then
  printf 'Invalid --timeout value: %s\n' "${timeout}" >&2
  exit 2
fi
if ! positive_int "${interval}"; then
  printf 'Invalid --interval value: %s\n' "${interval}" >&2
  exit 2
fi

target="${user}@${host}"
deadline=$((SECONDS + timeout))

printf 'Waiting up to %ss for SSH on %s...\n' "${timeout}" "${target}"
until ssh -o BatchMode=yes -o ConnectTimeout=5 "${target}" 'true' >/dev/null 2>&1; do
  if [ "${SECONDS}" -ge "${deadline}" ]; then
    printf 'Timed out waiting for SSH on %s.\n' "${target}" >&2
    exit 1
  fi
  sleep "${interval}"
done

printf 'SSH is reachable on %s; running make status...\n' "${target}"
remote_cd="$(remote_cd_target)"
ssh -o BatchMode=yes -o ConnectTimeout=10 "${target}" "cd ${remote_cd} && make status"
