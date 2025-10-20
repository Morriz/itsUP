#!/usr/bin/env bash
set -e

# Kill any existing instance
sudo pkill -f docker_monitor.py 2>/dev/null || true

# Ensure log file exists
sudo touch /var/log/compromised_container.log

# Parse flags
FLAGS=""
if [[ "$1" == "--skip-sync" ]]; then
    FLAGS="--skip-sync"
    echo "Starting with --skip-sync flag (will not sync OpenSnitch blocks to blacklist)"
fi

# Start in background with proper daemonization
cd "$(dirname "$0")/.."
sudo setsid python3 bin/docker_monitor.py $FLAGS < /dev/null &> /dev/null &

echo "Container security monitor started in background"
sleep 2

# Tail logs (trap INT to exit cleanly)
trap 'exit 0' INT TERM
tail -f /var/log/compromised_container.log
