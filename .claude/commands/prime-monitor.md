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
- Grace period (2s delay for timing issues)
- Configuration constants
- Network architecture
- Usage and troubleshooting

## Key Implementation Files

Familiarize yourself with:
- `monitor/core.py` - Main ContainerMonitor class
- `monitor/constants.py` - Configuration constants
- `monitor/opensnitch.py` - OpenSnitch integration
- `monitor/iptables.py` - iptables management
- `monitor/lists.py` - IP list management

## Recent Major Changes

1. **DNS Registry** - Persistent JSON storage (`data/dns-registry.json`) that survives restarts
2. **Grace Period** - 2-second delay before checking connections (handles docker logs buffering)
3. **File Locking** - Thread-safe registry writes with `_dns_registry_file_lock`
4. **No Container Restart Required** - Registry persistence eliminates false positives

You are now ready to work on the monitor system.
