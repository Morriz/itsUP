#!/usr/bin/env bash
# launchd has no native equivalent of systemd's ExecStop, but it DOES send
# SIGTERM to running agents at logout/shutdown. This wrapper bridges the gap:
# it runs the bringup sequence, then stays alive waiting on signals, so when
# launchd tears it down the trap fires `itsup down --clean` for graceful
# container shutdown. Same end-state as systemd's ExecStop, expressed via
# launchd's actual semantics.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"
# shellcheck disable=SC1091
source env.sh

shutdown_cleanly() {
    # Stop containers in dependency order but DO NOT remove them — leaves them
    # in `exited` state so Docker's restart policy brings them back sub-second
    # on next boot (vs minutes to recreate from compose).
    echo "[bringup-guardian] signal caught — running itsup down"
    itsup down
    exit 0
}
trap shutdown_cleanly TERM INT QUIT

# Bring core infra up, then deploy all projects.
itsup run
itsup apply

# Stay alive so launchd can signal us at shutdown for graceful teardown.
# `wait $!` on a backgrounded sleep is the canonical signal-responsive idle
# pattern in bash; a bare `sleep` doesn't always interrupt cleanly.
while true; do
    sleep 86400 &
    wait $! || true
done
