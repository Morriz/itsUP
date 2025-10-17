#!/bin/bash

if [ "$EUID" -ne 0 ]; then 
    echo "Run as root: sudo $0"
    exit 1
fi

echo "=== Configuring Docker Daemon DNS ==="
echo ""

# Backup existing config
if [ -f /etc/docker/daemon.json ]; then
    cp /etc/docker/daemon.json /etc/docker/daemon.json.backup.$(date +%Y%m%d_%H%M%S)
    echo "✓ Backed up existing daemon.json"
fi

# Create or update daemon.json
cat > /etc/docker/daemon.json.new << 'EOF'
{
  "dns": ["172.30.0.20", "192.168.1.1"],
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
EOF

# If existing config exists, we should merge
if [ -f /etc/docker/daemon.json ]; then
    echo ""
    echo "Current daemon.json:"
    cat /etc/docker/daemon.json
    echo ""
    echo "New daemon.json will be:"
    cat /etc/docker/daemon.json.new
    echo ""
    read -p "Replace existing config? (y/N): " confirm
    if [[ $confirm != [yY] ]]; then
        echo "Aborted. Manually edit /etc/docker/daemon.json and add:"
        echo '  "dns": ["172.30.0.20", "192.168.1.1"],'
        rm /etc/docker/daemon.json.new
        exit 1
    fi
fi

mv /etc/docker/daemon.json.new /etc/docker/daemon.json
echo "✓ Updated /etc/docker/daemon.json"
echo ""

echo "=== Restarting Docker Daemon ==="
systemctl restart docker
sleep 3

if systemctl is-active --quiet docker; then
    echo "✓ Docker daemon restarted successfully"
else
    echo "❌ Docker daemon failed to start!"
    echo "Restoring backup..."
    if [ -f /etc/docker/daemon.json.backup.* ]; then
        mv /etc/docker/daemon.json.backup.* /etc/docker/daemon.json
        systemctl restart docker
    fi
    exit 1
fi

echo ""
echo "=== Verification ==="
echo "Testing DNS from a new container:"
docker run --rm alpine nslookup google.com
echo ""

echo "✅ Complete! All containers will now use 172.30.0.20 (dns-honeypot) for DNS"
echo ""
echo "Next steps:"
echo "1. Start DNS honeypot: make dns-up"
echo "2. Start security monitor: make monitor-start"
echo "3. Restart your containers to pick up new DNS settings"
echo "4. Monitor the logs: make monitor-logs"
