# CLAUDE.md

Developer guide for working with this codebase. **Read [README.md](README.md) first** for architecture, components, and workflows.

## CRITICAL RULES (ADHERE AT ALL COSTS!)

🚨 **ALWAYS OPERATE FROM PROJECT ROOT** 🚨

- **NEVER** cd into subdirectories and stay there
- Use relative paths from root (e.g., `upstream/instrukt-ai/docker-compose.yml`)
- If you need to run a command in a subdirectory, use `(cd dir && command)`

🚨 **PYTHON UNDERSCORE NAMING CONVENTION** 🚨

- **ALWAYS** use single leading underscore `_` for instance variables that are internal/private
- **NEVER** use leading underscore for public API (methods/variables intended for external use)
- **Rule**: If it's not part of the public interface, prefix with `_`
- **Example**:

  ```python
  class MyClass:
      def __init__(self):
          # Public config (external callers need these)
          self.enabled = True
          self.mode = "production"

          # Private state (internal implementation only)
          self._cache = {}
          self._lock = threading.Lock()
          self._internal_counter = 0

      # Public API methods (no underscore)
      def run(self):
          pass

      def get_status(self):
          return self._internal_counter

      # Private helper methods (underscore prefix)
      def _update_cache(self):
          pass
  ```

- **Be consistent!** Don't mix conventions within the same class

🚨 **NEVER MODIFY OR MOVE OPENSNITCH DATABASE** 🚨

- OpenSnitch database (`/var/lib/opensnitch/opensnitch.sqlite3`) is the **permanent security audit log**
- NEVER run DELETE queries against this database for ANY reason
- NEVER move, rename, copy, or modify the database file itself
- NEVER use `mv`, `cp`, or any file operations on `/var/lib/opensnitch/opensnitch.sqlite3`
- The database is **read-only** for SELECT queries ONLY
- Historical block data is critical for security analysis and forensics
- Handle false positives by modifying whitelist/blacklist files and iptables rules, NEVER by touching the database
- For testing missing DB scenarios, use mock paths like `/tmp/nonexistent.db`, NEVER move production database

## V2 Architecture Overview

itsUP V2 uses a **configuration-as-code** approach with git submodules:

- **`projects/`**: Git submodule containing service configurations (YAML files)
- **`secrets/`**: Git submodule containing encrypted secrets (SOPS)
- **`samples/`**: Sample configuration templates for initialization

### Configuration Structure

**Main Configuration (`projects/traefik.yml`):**

The central configuration file defines:
- Domain suffix for automatic subdomain routing
- Let's Encrypt settings and email
- Trusted IP ranges (for rate limiting bypass)
- Traefik settings (log level, dashboard)
- Middleware configuration (rate limiting, security headers)
- Plugin configuration (CrowdSec, etc.)
- Version pins for containers

**Secrets Management (`secrets/global.txt`):**

Encrypted with SOPS, contains sensitive values:
- `LETSENCRYPT_EMAIL`: Email for Let's Encrypt cert notifications
- `TRAEFIK_ADMIN`: htpasswd for Traefik dashboard
- `CROWDSEC_API_KEY`: CrowdSec bouncer API key
- `CROWDSEC_CAPI_MACHINE_ID`: CrowdSec CAPI credentials
- `CROWDSEC_CAPI_PASSWORD`: CrowdSec CAPI password

Variables are referenced in `traefik.yml` as `${VAR_NAME}` and expanded at runtime.

## Common Development Commands

### Setup and Installation

**First-time setup requires git submodules:**

The `projects/` and `secrets/` directories are git submodules that MUST be initialized. Users must create their own private repositories for these and add them as submodules. See [README.md](README.md) for detailed submodule setup instructions.

```bash
# After setting up submodules (see README.md)
./itsup init                # Initialize from samples (interactive validation)
make install                # Create .venv and install dependencies
bin/apply.py                # Apply configuration with zero-downtime updates
```

**What `itsup init` does:**
- Validates that `projects/` and `secrets/` submodules are initialized
- Copies sample files (won't overwrite existing files):
  - `samples/env` → `.env`
  - `samples/traefik.yml` → `projects/traefik.yml`
  - `samples/secrets/global.txt` → `secrets/global.txt`
- Provides next steps for configuration

**Note:** `bin/apply.py` uses smart change detection via config hash comparison - only performs rollouts when changes detected.

### Testing and Validation

```bash
bin/test.sh                 # Run all Python unit tests (*_test.py files)
bin/lint.sh                 # Run linting
bin/format.sh               # Format code
```

### Monitoring and Logs

```bash
bin/tail-logs.sh            # Tail all logs (Traefik, API, errors) with flat formatting
make logs                   # Same as above
```

### Utilities

```bash
bin/write-artifacts.py      # Regenerate proxy and upstream configs without deploying
bin/backup.py               # Backup upstream/ directory to S3
bin/requirements-update.sh  # Update Python dependencies
```

### Docker Management

V2 uses direct `docker compose` commands from the project root:

```bash
# Proxy management
docker compose -f proxy/docker-compose.yml ps
docker compose -f proxy/docker-compose.yml logs -f traefik

# Upstream service management (example: whoami project)
docker compose -f upstream/whoami/docker-compose.yml ps
docker compose -f upstream/whoami/docker-compose.yml logs -f

# Smart updates with change detection
bin/apply.py                # Apply all configuration changes with zero-downtime
```

**Note:** The old `dcp`/`dcu` shell functions from `lib/functions.sh` are deprecated in V2. Use `bin/apply.py` for smart updates or direct `docker compose` commands for manual operations.

## Implementation Patterns

### Template Generation

All Docker Compose files are generated from Jinja2 templates:

- `tpl/upstream/docker-compose.yml.j2`: Upstream service deployments
- `tpl/proxy/docker-compose.yml.j2`: Proxy stack
- `tpl/proxy/routers-{http,tcp,udp}.yml.j2`: Traefik dynamic configuration

Templates have access to:

- `project`: Project object with all services
- Pydantic enum types (Protocol, Router, ProxyProtocol)
- Python builtins (isinstance, len, list, str)

### Filtering Pattern

Many functions accept filter callbacks with variable arity:

```python
get_projects(filter=lambda p: p.enabled)                          # Filter by project
get_projects(filter=lambda p, s: s.image)                         # Filter by service
get_projects(filter=lambda p, s, i: i.router == Router.http)      # Filter by ingress
```

The system detects arity via `filter.__code__.co_argcount` and filters at the appropriate level.

### Plugin System

Plugins are configured in `projects/traefik.yml` under the `plugins:` section. Currently supported:

**CrowdSec:**

Configuration in `projects/traefik.yml`:
```yaml
plugins:
  crowdsec:
    enabled: true
    version: v1.2.0
    collections:
      - crowdsecurity/linux
      - crowdsecurity/traefik
    scenarios:
      - crowdsecurity/http-admin-interface-probing
      - crowdsecurity/http-backdoors-attempts
    options:
      logLevel: WARN
      updateIntervalSeconds: 60
      defaultDecisionSeconds: 600
      httpTimeoutSeconds: 10
      # Secrets from secrets/global.txt
      apikey: ${CROWDSEC_API_KEY}
      capiMachineId: ${CROWDSEC_CAPI_MACHINE_ID}
      capiPassword: ${CROWDSEC_CAPI_PASSWORD}
```

Plugin models are validated and loaded dynamically at runtime.

## Testing

- Framework: Python `unittest`
- Naming: `*_test.py` files
- Run: `bin/test.sh` or `make test`
- Key test files:
  - `lib/upstream_test.py`: Upstream generation
  - `bin/backup_test.py`: Backup functionality
  - `bin/write_artifacts_test.py`: Artifact generation
  - `bin/migrate_v2_test.py`: V2 migration tests
