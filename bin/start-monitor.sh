#!/usr/bin/env bash
set -e

# Kill any existing instance
sudo pkill -f docker_monitor.py 2>/dev/null || true

# Ensure log file exists
sudo touch /var/log/compromised_container.log

# Parse flags
FLAGS=""
for arg in "$@"; do
    case "$arg" in
        --skip-sync)
            FLAGS="$FLAGS --skip-sync"
            ;;
        --block)
            FLAGS="$FLAGS --block"
            ;;
    esac
done

if [[ -n "$FLAGS" ]]; then
    echo "Starting with flags:$FLAGS"
fi

# Start in background with proper daemonization
cd "$(dirname "$0")/.."
sudo setsid python3 bin/docker_monitor.py $FLAGS < /dev/null &> /dev/null &

echo "Container security monitor started in background"
sleep 2

# Tail logs (trap INT to exit cleanly)
trap 'exit 0' INT TERM
tail -f /var/log/compromised_container.log
