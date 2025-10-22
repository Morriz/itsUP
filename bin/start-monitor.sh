#!/usr/bin/env bash
set -e

# Kill any existing instance
sudo pkill -f docker_monitor.py 2>/dev/null || true

# Ensure log file exists
sudo touch /var/log/compromised_container.log

# Parse flags - just pass them through directly
FLAGS="$@"

if [[ -n "$FLAGS" ]]; then
    echo "Starting with flags: $FLAGS"
fi

# Start in background with proper daemonization
cd "$(dirname "$0")/.."
sudo setsid python3 bin/docker_monitor.py $FLAGS < /dev/null &> /dev/null &

echo "Container security monitor started in background"
sleep 2

# Show startup logs and continue tailing (trap INT to exit cleanly)
trap 'exit 0' INT TERM
tail -n 50 -f /var/log/compromised_container.log
