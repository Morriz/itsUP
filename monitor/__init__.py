"""
Container Security Monitor - Modular architecture.

This package provides hardcoded IP detection for containers by correlating
DNS queries with outbound connections.
"""

from .constants import (
    BLACKLIST_FILE,
    CHECK_CONNECTIONS_INTERVAL,
    CONNECTION_DEDUP_WINDOW,
    DNS_CACHE_WINDOW_HOURS,
    DOCKER_NETWORK_CIDR,
    HONEYPOT_CONTAINER,
    IPTABLES_CHAIN,
    IPTABLES_DROP_COMMENT,
    IPTABLES_LOG_PREFIX,
    LOG_FILE,
    LOG_LEVEL,
    OPENSNITCH_DB,
    OPENSNITCH_POLL_INTERVAL,
    PERIODIC_TASK_INTERVAL,
    PRIVATE_IP_RANGES,
    PROJECT_ROOT,
    RECENT_CONNECTIONS_BUFFER_SIZE,
    SERVER_PORTS,
    WHITELIST_FILE,
)
from .iptables import IptablesManager
from .lists import IPList
from .opensnitch import OpenSnitchIntegration

__all__ = [
    # Constants
    "BLACKLIST_FILE",
    "CHECK_CONNECTIONS_INTERVAL",
    "CONNECTION_DEDUP_WINDOW",
    "DNS_CACHE_WINDOW_HOURS",
    "DOCKER_NETWORK_CIDR",
    "HONEYPOT_CONTAINER",
    "IPTABLES_CHAIN",
    "IPTABLES_DROP_COMMENT",
    "IPTABLES_LOG_PREFIX",
    "LOG_FILE",
    "LOG_LEVEL",
    "OPENSNITCH_DB",
    "OPENSNITCH_POLL_INTERVAL",
    "PERIODIC_TASK_INTERVAL",
    "PRIVATE_IP_RANGES",
    "PROJECT_ROOT",
    "RECENT_CONNECTIONS_BUFFER_SIZE",
    "SERVER_PORTS",
    "WHITELIST_FILE",
    # Classes
    "IptablesManager",
    "IPList",
    "OpenSnitchIntegration",
]
