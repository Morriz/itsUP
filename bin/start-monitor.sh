#!/usr/bin/env bash
set -e

log_file="logs/monitor.log"
# Kill any existing instance
sudo pkill -f docker_monitor.py 2>/dev/null || true

# Ensure log file exists
sudo touch "$log_file"

# Parse flags - just pass them through directly
FLAGS="$@"

if [[ -n "$FLAGS" ]]; then
    echo "Starting with flags: $FLAGS"
fi

# Preserve LOG_LEVEL if set
if [[ -n "$LOG_LEVEL" ]]; then
    echo "Using log level: $LOG_LEVEL"
    ENV_VARS="LOG_LEVEL=$LOG_LEVEL"
else
    ENV_VARS=""
fi

# Start in background with proper daemonization
sudo $ENV_VARS setsid python3 bin/docker_monitor.py $FLAGS < /dev/null &> /dev/null &

echo "Container security monitor started in background"
echo "View logs: tail -f $log_file"
