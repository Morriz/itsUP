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

## Common Development Commands

### Setup and Installation

**First-time setup requires git submodules:**

The `projects/` and `secrets/` directories are git submodules that MUST be initialized before running `bin/install.py`. Users must create their own private repositories for these and add them as submodules. See [README.md](README.md) for detailed submodule setup instructions.

```bash
# After initializing submodules (see README.md)
bin/install.py              # Validates submodules, copies samples, creates .venv, installs deps
bin/start-all.sh            # Start proxy and API server
bin/apply.py                # Apply configuration with smart zero-downtime updates
```

**What `bin/install.py` does:**
- Validates that `projects/` and `secrets/` submodules are initialized
- Copies sample files (won't overwrite existing files):
  - `samples/env` → `.env`
  - `samples/traefik.yml` → `projects/traefik.yml`
  - `samples/secrets/global.txt` → `secrets/global.txt`
- Creates Python virtual environment
- Installs dependencies from `requirements-prod.txt`

**Note:** `bin/apply.py` uses smart change detection via config hash comparison - only performs rollouts when changes detected.

### Testing and Validation

```bash
bin/test.sh                 # Run all Python unit tests (*_test.py files)
bin/lint.sh                 # Run linting
bin/format.sh               # Format code
bin/validate-db.py          # Validate db.yml schema
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

### Shell Utility Functions

Source `lib/functions.sh` to get helper functions:

```bash
source lib/functions.sh

dcp <cmd> [service]         # Smart proxy management
                            # - dcp up [service]: Smart update (detects changes)
                            # - dcp restart [service]: Smart restart
                            # - Other commands pass through to docker compose

dcu <project> <cmd> [svc]   # Smart upstream management
                            # - dcu project up [service]: Smart update with auto-rollout
                            # - dcu project restart [service]: Smart restart
                            # - Other commands pass through to docker compose

dca <cmd>                   # Run docker compose command for all upstream projects
dcpx <service> <cmd>        # Execute command in proxy container
dcux <project> <svc> <cmd>  # Execute command in upstream service container
```

**Smart Behavior:**

- `up` and `restart` commands call Python's `update_proxy()`/`update_upstream()` which use config hash comparison
- Only performs zero-downtime rollout when actual changes detected
- Other commands pass through directly to docker compose

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

Plugins configured in `db.yml` under `plugins:` section. Currently supported:

**CrowdSec:**

- `enabled`: Enable/disable plugin
- `apikey`: Bouncer API key from CrowdSec container
- `version`: Plugin version
- `options`: Plugin-specific settings (log level, timeouts, CAPI credentials)

Plugins instantiated using dynamic model loading in `lib/data.py:get_plugin_model()`.

## Testing

- Framework: Python `unittest`
- Naming: `*_test.py` files
- Run: `bin/test.sh`
- Key test files:
  - `lib/data_test.py`: Database operations
  - `lib/upstream_test.py`: Upstream generation
  - `bin/backup_test.py`: Backup functionality
