---
description: Prime context for working on the Container Security Monitor
---

You are now working on the **Container Security Monitor** system. Read and understand the following key documentation:

## Product Requirements Document

Read the PRD at `prds/monitor.md` to understand:
- Functional requirements (FR1-FR9)
- Design decisions
- OpenSnitch integration architecture
- Modes of operation

## User Guide & Implementation

Read the user guide at `monitor/README.md` to understand:
- System architecture and components
- DNS Registry implementation (persistent storage)
- Grace period (3s delay for timing issues)
- Configuration constants
- Network architecture
- Usage and troubleshooting

## Key Implementation Files

Familiarize yourself with:
- `bin/docker_monitor.py` - Entry point script (runs as root)
- `bin/start-monitor.sh` - Start/restart script (kills old instance, starts new)
- `monitor/core.py` - Main ContainerMonitor class with threading
- `monitor/constants.py` - Configuration constants
- `monitor/opensnitch.py` - OpenSnitch integration
- `monitor/iptables.py` - iptables management
- `monitor/lists.py` - IP list management

## How the Monitor Runs

**CRITICAL**: The monitor is NOT a Docker container. It runs as a **standalone Python process on the host** (requires root).

- **Current process**: `python3 bin/docker_monitor.py` (check with `ps aux | grep docker_monitor.py`)
- **Log file**: `logs/monitor.log` (view with `tail -f logs/monitor.log`)
- **Start/Restart**: `bin/start-monitor.sh [flags]` (auto-kills old instance)
- **Stop**: `sudo pkill -f docker_monitor.py`

## Monitor Modes & Flags

- `--report-only` - Detection only, no iptables blocking
- `--use-opensnitch` - Enable OpenSnitch integration for cross-reference
- `--skip-sync` - Memory-only mode (no file I/O)
- `--cleanup` - Validate blacklist against OpenSnitch DB
- `--clear-iptables` - Remove all monitor iptables rules

## Monitoring Threads

The monitor runs 5-6 concurrent threads:
1. **Docker events** - Track container start/stop for IP mapping
2. **DNS honeypot** - Parse dns-honeypot container logs for DNS queries
3. **Direct connections** - Monitor journalctl for [CONTAINER-TCP] kernel logs
4. **Connection checker** - Check queued connections against DNS cache (with 3s grace period)
5. **Periodic tasks** - Update container mappings, reload IP lists (every 5s)
6. **OpenSnitch monitor** (optional) - Poll OpenSnitch DB for blocks

## Recent Major Changes

1. **DNS Registry** - Persistent JSON storage (`data/dns-registry.json`) that survives restarts
2. **Grace Period** - 3-second delay before checking connections (handles docker logs buffering)
3. **File Locking** - Thread-safe registry writes with `_dns_registry_file_lock`
4. **No Container Restart Required** - Registry persistence eliminates false positives

## Troubleshooting

If logs stop appearing:
1. Check if monitor is running: `ps aux | grep docker_monitor.py`
2. Check log file: `tail -f logs/monitor.log`
3. Check DNS honeypot: `docker logs dns-honeypot --tail 20`
4. Check kernel logs: `journalctl -k -n 20 | grep CONTAINER-TCP`
5. Restart monitor: `bin/start-monitor.sh`

You are now ready to work on the monitor system.
