#!/bin/bash
# Backup Docker container logs to logs/docker/ for long-term retention

set -e

BACKUP_DIR="logs/docker"
mkdir -p "$BACKUP_DIR"

# Get all running containers from itsUP stacks
for container in $(docker ps --filter "label=com.docker.compose.project" --format "{{.Names}}"); do
    container_id=$(docker inspect "$container" --format '{{.Id}}')
    service=$(docker inspect "$container" --format '{{index .Config.Labels "com.docker.compose.service"}}')
    project=$(docker inspect "$container" --format '{{index .Config.Labels "com.docker.compose.project"}}')
    
    service_dir="$BACKUP_DIR/${project}-${service}"
    mkdir -p "$service_dir"
    
    # Copy rotated logs (not the current one being written to)
    for log in /var/lib/docker/containers/${container_id}/*-json.log.[0-9]*; do
        if [ -f "$log" ]; then
            basename=$(basename "$log")
            timestamp=$(stat -c %Y "$log")
            dated_name="${project}-${service}-${timestamp}.json.gz"
            
            # Only backup if not already backed up
            if [ ! -f "$service_dir/$dated_name" ]; then
                sudo gzip -c "$log" > "$service_dir/$dated_name"
                echo "Backed up: $dated_name"
            fi
        fi
    done
done

echo "Docker log backup complete"
