# V2.0.0 - File-Based Configuration Architecture

## Breaking Changes

**Migration from V1 to V2 required** - see Migration Guide below.

### Removed V1 Features

- **db.yml** - No longer required for core functionality

### New Requirements

- **projects/ and secrets/ directories** - Must be created (see Migration Guide)
- **SOPS + age** - Required for secret encryption

---

## What's New

### File-Based Configuration System

Replace monolithic `db.yml` with git-based projects/ structure:

- Each project: `docker-compose.yml` + `ingress.yml`
- Infrastructure overrides: `projects/traefik.yml`
- Encrypted secrets: `secrets/*.enc.txt` (SOPS)
- Everything in version control (except SOPS key)

**Benefits:**

- Shareable infrastructure (public projects/ repo)
- Standard docker-compose.yml format
- Clear secret separation with encryption
- Full version control for all configuration
- No database to manage or migrate

### SOPS Encryption Integration

Complete secret management workflow:

- **Auto-detection**: Tries encrypted files first, falls back to plaintext
- **Memory-only decryption**: Secrets never hit disk when loading
- **Seamless editing**: `itsup edit-secret` handles decrypt→edit→encrypt→cleanup
- **Key management**: Generate, rotate, and backup encryption keys
- **Auto-encrypt on commit**: Warns and encrypts before committing

**Commands:**

```bash
itsup sops-key              # Generate encryption key + update .sops.yaml
itsup sops-key --rotate     # Rotate key + re-encrypt all secrets
itsup edit-secret itsup     # Edit secret (temp file, auto-cleanup)
itsup encrypt               # Encrypt all plaintext secrets
itsup encrypt --delete      # Encrypt + delete plaintext
itsup decrypt               # Decrypt for manual editing (warns about persistence)
```

### Complete CLI Rewrite

Comprehensive command-line interface:

**Initialization:**

```bash
itsup init                  # Initialize projects/ and secrets/ repos from samples
itsup status                # Show git status for both repos
itsup commit                # Auto-generated messages, detects key rotation
```

**Stack Management:**

```bash
itsup run                   # Orchestrated startup: dns→proxy→api→monitor
itsup down                  # Stop all containers
itsup down --clean          # Stop + remove itsUP containers
```

**Stack-Specific Operations:**

```bash
itsup dns up/down/restart/logs
itsup proxy up/down/restart/logs [service]
itsup monitor start/stop/logs/cleanup/report
```

**Project Operations:**

```bash
itsup apply                 # Apply all configurations (regenerate + deploy)
itsup apply <project>       # Apply single project
itsup svc <proj> <cmd>      # Docker compose passthrough (up/down/logs/exec)
itsup validate              # Validate project configurations
```

### Smart Change Detection

Intelligent deployment optimization:

- **Config hash comparison**: Only redeploys when changes detected
- **Zero-downtime updates**: Health checks + graceful switchover (stateless apps only)
- **Parallel deployment**: Concurrent upstream project deployment
- **Rollback safety**: Preserves previous version until new one healthy (stateless apps only)

### Template-Based Generation

Minimal Jinja2 templates with deep merge:

- `tpl/proxy/traefik.yml.j2` - Base Traefik configuration
- `tpl/proxy/docker-compose.yml.j2` - Proxy stack
- User overrides in `projects/traefik.yml` merged on top
- Auto-generated Traefik labels from `ingress.yml`

### Container Security Monitor Integration

Enhanced monitoring with automatic policy generation:

- **iptables integration**: Block network access for suspicious containers
- **Auto-whitelist**: Learn from legitimate traffic patterns
- **Threat reporting**: Generate intelligence reports
- **OpenSnitch support**: Optional GUI-based firewall integration

---

## Migration Guide

### For New Users

1. **Clone and install:**

```bash
git clone <repo>
cd itsup
make install
source env.sh
```

2. **Initialize configuration:**

```bash
itsup init
# Creates projects/ and secrets/ directories
# Copies sample files
```

3. **Generate SOPS key:**

```bash
itsup sops-key
itsup commit
```

4. **Edit secrets:**

```bash
itsup edit-secret itsup
itsup commit
```

5. **Deploy:**

```bash
itsup apply
itsup run
```

### For Existing Users

No migration needed - V2 is additive:

- Existing workflows continue to work
- New file-based configuration available via `projects/` and `secrets/`
- Use `itsup init` to set up the new directories
- Gradually migrate projects to new structure

---

## Technical Changes

### Architecture

- **Data layer**: db.yml → Git repositories
- **Configuration**: One YAML file → Directory structure with YAML files
- **Secrets**: Plain env vars → SOPS encrypted
- **CLI**: Click framework with command groups
- **Deployment**: Smart change detection with health checks

### File Structure

```
itsUP/
├── projects/           # Independent git repo (gitignored)
│   ├── traefik.yml    # Infrastructure overrides
│   └── {project}/
│       ├── docker-compose.yml
│       └── ingress.yml
├── secrets/           # Independent git repo (gitignored)
│   ├── .sops.yaml    # SOPS configuration
│   ├── itsup.enc.txt # Encrypted secrets
│   └── {project}.enc.txt
├── commands/          # CLI command modules
├── lib/              # Core logic (data, models, sops)
├── tpl/              # Jinja2 templates
└── bin/              # Utility scripts
```

### Dependencies

**Added:**

- `sops` - Secret encryption
- `age` - Encryption backend
- `click` - CLI framework
- `jinja2` - Templating

### Code Organization

- `lib/data.py` - V2 data loading (replaces database queries)
- `lib/models.py` - IngressV2, TraefikConfig models
- `lib/sops.py` - Encryption/decryption helpers
- `commands/*.py` - Modular CLI commands

---

## Testing

**Unit tests:** 87 tests (all passing)

**Test coverage:**

- ✅ Data loading and validation
- ✅ Upstream generation with label injection
- ✅ SOPS encryption/decryption (core functionality in lib/sops.py)
- ✅ CLI command validation (help, error handling)
- ✅ Template rendering

**Run tests:**

```bash
make test
```

---

## Documentation Updates

- ✅ README.md - Complete V2 workflow
- ✅ CLAUDE.md - Development guide updated
- ✅ prds/v2.md - Architecture and requirements
- ⏳ API documentation (pending)

---

## Contributors

This release was developed with assistance from Claude (Anthropic).

## Versioning

**Version:** 2.0.0 (Semantic Versioning)

- Major version bump due to breaking changes
- V1 available on `v1-legacy` branch if needed

## Next Steps

**Post-V2 Roadmap:**

- [ ] Holiday in the tropics
- [ ] Drink from a coconut
