#!/usr/bin/env bash
set -e

# Trap Ctrl-C and exit cleanly
trap 'echo "❌ Restart cancelled"; exit 130' INT TERM

echo "🔄 Restarting all containers (excluding dns-honeypot)..."

# Restart proxy services
echo "🔄 Restarting proxy services..."
docker-compose -f proxy/docker-compose.yml restart

# Restart all upstream projects
if [ -d "upstream" ]; then
    for dir in upstream/*/; do
        if [ -d "$dir" ]; then
            project=$(basename "$dir")
            echo "🔄 Restarting upstream/$project..."
            docker-compose --project-directory "$dir" -p "$project" -f "$dir/docker-compose.yml" restart
        fi
    done
fi

echo "✅ All containers restarted"
