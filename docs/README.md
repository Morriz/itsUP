# itsUP Documentation

Technical documentation for the itsUP infrastructure management system.

## Documentation Index

### Architecture & Components
- [Architecture Overview](architecture.md) - System architecture, components, and data flow
- [Networking](networking.md) - Network topology, DNS, proxying, and routing

### Core Infrastructure
- [DNS Stack](stacks/dns.md) - DNS honeypot and container networking
- [Proxy Stack](stacks/proxy.md) - Traefik, dockerproxy, CrowdSec integration
- [API Server](stacks/api.md) - REST API for infrastructure management

### Operations
- [Logging](operations/logging.md) - Log management, rotation, and analysis
- [Security Monitoring](operations/monitoring.md) - Container security monitor, threat detection
- [Backups](operations/backups.md) - Backup strategies and S3 integration
- [Deployment](operations/deployment.md) - Zero-downtime deployments and rollouts

### Development
- [Project Structure](development/structure.md) - Codebase layout and conventions
- [Configuration](development/configuration.md) - Project configs, secrets, and templates
- [Testing](development/testing.md) - Test framework and coverage

### Reference
- [CLI Commands](reference/cli.md) - Complete itsup command reference
- [Environment Variables](reference/env-vars.md) - Environment variable documentation
- [Troubleshooting](reference/troubleshooting.md) - Common issues and solutions

## Quick Links

- [Main README](../README.md) - Getting started and overview
- [CLAUDE.md](../CLAUDE.md) - Developer guide for working with this codebase
- [Security Documentation](security.md) - Security architecture and policies
