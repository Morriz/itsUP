"""
Configuration constants for Container Security Monitor.

This module contains all configuration values, file paths, and hardcoded
settings used throughout the monitoring system.
"""
import os
from dotenv import load_dotenv

# Load .env file from project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

# File Paths
LOG_FILE = "/var/log/compromised_container.log"
OPENSNITCH_DB = os.getenv("OPENSNITCH_DB", "/var/lib/opensnitch/opensnitch.sqlite3")
BLACKLIST_FILE = os.path.join(PROJECT_ROOT, "data", "blacklist", "blacklist-outbound-ips.txt")
WHITELIST_FILE = os.path.join(PROJECT_ROOT, "data", "whitelist", "whitelist-outbound-ips.txt")
DNS_REGISTRY_FILE = os.path.join(PROJECT_ROOT, "data", "dns-registry.json")

# Container Names
HONEYPOT_CONTAINER = "dns-honeypot"

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Time Windows (in seconds unless specified)
DNS_CACHE_WINDOW_HOURS = 48  # Hours of docker logs to parse for initial DNS registry bootstrap
CONNECTION_DEDUP_WINDOW = 60  # Deduplicate same connection within 60 seconds
OPENSNITCH_POLL_INTERVAL = 0.5  # Poll OpenSnitch DB every 0.5 seconds
PERIODIC_TASK_INTERVAL = 5  # Run periodic tasks (container mapping, list updates) every 5 seconds
CHECK_CONNECTIONS_INTERVAL = 0.5  # Check direct connections queue every 0.5 seconds

# Buffer Sizes
RECENT_CONNECTIONS_BUFFER_SIZE = 100  # Keep last 100 direct connections in memory

# Network Configuration
SERVER_PORTS = {8443}  # Traefik's listening port (inbound traffic indicator)
DOCKER_NETWORK_CIDR = "172.0.0.0/8"  # Docker internal network range

# iptables Configuration
IPTABLES_CHAIN = "DOCKER-USER"  # Chain where rules are inserted
IPTABLES_LOG_PREFIX = "[CONTAINER-TCP] "  # Prefix for kernel log entries
IPTABLES_DROP_COMMENT = "BLOCKED-CONTAINER-IP"  # Comment for DROP rules

# Private IP Ranges (RFC 1918 + link-local)
# These IPs are excluded from threat detection
PRIVATE_IP_RANGES = {
    "10.0.0.0/8",          # Class A private
    "172.16.0.0/12",       # Class B private
    "192.168.0.0/16",      # Class C private
    "127.0.0.0/8",         # Loopback
    "169.254.0.0/16",      # Link-local
}
