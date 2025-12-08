# CLAUDE.md

Developer guide for working with this codebase. **Read [README.md](README.md) first** for architecture, components, and workflows.

## CRITICAL RULES (ADHERE AT ALL COSTS!)

🚨 **ALWAYS OPERATE FROM PROJECT ROOT** 🚨

- **NEVER** cd into subdirectories and stay there
- Use relative paths from root (e.g., `upstream/instrukt-ai/docker-compose.yml`)
- If you need to run a command in a subdirectory, use `(cd dir && command)`

🚨 **CODE FORMATTING AND LINTING** 🚨

- **ALWAYS** use the exact same commands as pre-commit hooks to avoid formatting loops
- **Pre-commit runs:** `bin/format.sh` → `bin/lint.sh` → `bin/test.sh`
- **Commands:**
  ```bash
  bin/format.sh    # isort + black on api/ and lib/
  bin/lint.sh      # pylint + mypy
  bin/test.sh      # Run all *_test.py files
  ```
- **Before committing:** Run `bin/format.sh` manually to ensure files are formatted correctly

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

🚨 **THIS REPO DOES NOT CONTAINERIZE ITS OWN CODE** 🚨

- **NEVER** containerize the itsUP codebase itself (Python code, CLI, API)
- **Reason:** Traefik runs on host network for zero-downtime deployments via scaling
- **What IS containerized:** Upstream project services (user workloads)
- **What is NOT containerized:**
  - DNS honeypot management code
  - Proxy/Traefik configuration code
  - API server (runs as Python process via `bin/start-api.sh`)
  - CLI tool (`itsup`)
  - All monitoring and management scripts
- This is an architectural decision for operational flexibility and zero-downtime

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

**First-time setup:**

1. **Install Python dependencies + bringup service** (MUST be done first):
   ```bash
   make install             # Installs deps and installs/enables systemd bringup service (itsup run && itsup apply on boot)
   ```

2. **Add itsup to PATH** (recommended):
   ```bash
   source env.sh            # Activates venv, adds bin/ to PATH, enables shell completion
   ```

   To make this permanent, add to your `~/.bashrc` or `~/.zshrc`:
   ```bash
   source /path/to/itsup/env.sh
   ```

   This enables:
   - Python virtual environment activation
   - `itsup` command in PATH
   - Tab completion for commands, options, and project names

3. **Initialize configuration** (prompts for git repos if needed):
   ```bash
   itsup init               # Clone/setup projects/ and secrets/ repos, copy samples
   ```

**What `itsup init` does:**

- Prompts for git URLs and clones `projects/` and `secrets/` repos (if not present)
- Copies sample files (won't overwrite existing files):
  - `samples/env` → `.env`
  - `samples/itsup.yml` → `projects/itsup.yml` (infrastructure config with secrets)
  - `samples/traefik.yml` → `projects/traefik.yml`
  - `samples/example-project/` → `projects/example-project/`
  - `samples/secrets/itsup.txt` → `secrets/itsup.txt`
- Init is idempotent - can be run multiple times safely

**Deploy:**
```bash
itsup apply                 # Apply all configurations (regenerate + deploy in parallel)
itsup apply <project>       # Apply single project configuration
```

**System service (auto boot):**
```bash
sudo systemctl status itsup-bringup.service   # runs itsup run && itsup apply at boot, down --clean on shutdown
sudo systemctl list-timers itsup-apply.timer  # nightly itsup apply at 03:00 via systemd timer
sudo systemctl list-timers itsup-backup.timer # nightly backup at 05:00 via systemd timer
sudo systemctl list-timers pi-healthcheck.timer # healthcheck every 5 min (strike window logic)

Git hook (auto requirements install):
```bash
git config core.hooksPath bin/hooks
```
This enables post-merge hook to pip install if any `requirements*.txt` changed.
```

**Note:** `itsup apply` (without project arg) deploys all projects in parallel. Uses smart change detection via config hash comparison - only performs rollouts when changes detected.

### Stack Management

**Orchestrated Operations:**

```bash
itsup run                              # Run complete stack (orchestrated: dns→proxy→api→monitor in report-only mode)
itsup down                             # Stop EVERYTHING (all projects + infrastructure, in parallel)
itsup down --clean                     # Stop everything + cleanup (removes stopped itsUP containers in parallel)
```

**Stack-Specific Operations:**

Every stack follows the same pattern: `up`, `down`, `restart`, `logs [service]`

```bash
# DNS stack (creates proxynet network)
itsup dns up                         # Start DNS stack
itsup dns down                       # Stop DNS stack
itsup dns restart                    # Restart DNS stack
itsup dns logs                       # Tail DNS stack logs

# Proxy stack (Traefik + dockerproxy)
itsup proxy up                       # Start proxy stack
itsup proxy up traefik               # Start only Traefik
itsup proxy down                     # Stop proxy stack
itsup proxy restart                  # Restart proxy stack
itsup proxy logs                     # Tail all proxy logs
itsup proxy logs traefik             # Tail Traefik logs only
```

**Directory → Command Mapping:**

- `dns/docker-compose.yml` → `itsup dns`
- `proxy/docker-compose.yml` → `itsup proxy`
- `upstream/project/` → `itsup svc project`

**Orchestrated vs Stack Operations:**

- `itsup run` = Full orchestrated startup (dns→proxy→api→monitor in report-only mode) in correct dependency order
- `itsup down` = Full orchestrated shutdown (monitor→api→ALL PROJECTS→proxy→dns) - projects stopped in parallel
- `itsup down --clean` = Shutdown + cleanup - removes stopped containers from itsUP-managed stacks (in parallel)
- `itsup dns up` = Stack-specific operation (just DNS)
- `itsup proxy up` = Stack-specific operation (just proxy)
- Different semantics: `run`/`down` do everything, stack commands are surgical

**Note**: `itsup run` starts the monitor in report-only mode (detection without blocking). For full protection with active blocking, use `itsup monitor start` after infrastructure is running.

### Project Service Management

```bash
itsup svc <project> <cmd> [service]  # Docker compose operations for project services
itsup svc <project> up               # Start all services in project
itsup svc <project> up <service>     # Start specific service
itsup svc <project> down             # Stop all services in project
itsup svc <project> restart          # Restart all services
itsup svc <project> logs -f          # Tail logs for all services
itsup svc <project> logs -f <svc>    # Tail logs for specific service
itsup svc <project> exec <svc> sh    # Execute shell in service container
```

**Tab Completion:** Project names, docker compose commands, and service names all support tab completion.

### Container Security Monitor

```bash
itsup monitor start                  # Start monitor with full protection
itsup monitor start --report-only    # Detection only, no blocking
itsup monitor start --use-opensnitch # With OpenSnitch integration
itsup monitor stop                   # Stop monitor
itsup monitor logs                   # Tail monitor logs
itsup monitor cleanup                # Review and cleanup blacklist
itsup monitor report                 # Generate threat intelligence report
```

### Testing and Validation

```bash
bin/test.sh                 # Run all Python unit tests (*_test.py files)
bin/lint.sh                 # Run linting
bin/format.sh               # Format code
itsup validate              # Validate all project configurations
itsup validate <project>    # Validate single project configuration
```

🚨 **ALWAYS TEST CODE AFTER CHANGES!!!!!** 🚨

### Makefile (Development Tools)

The Makefile is minimal and focused on development workflow:

```bash
make help                   # Show available targets
make install                # Install dependencies (calls itsup init)
make test                   # Run all tests
make lint                   # Run linter
make format                 # Format code
make clean                  # Remove generated artifacts
```

**Note:** For runtime operations (start/stop/logs/monitor), use `itsup` commands instead.

### Artifact Generation

```bash
itsup apply               # Regenerate all artifacts + deploy
itsup apply <project>     # Regenerate single project + deploy
bin/write_artifacts.py      # Regenerate proxy and upstream configs WITHOUT deploying (for testing)
```

### Utilities

```bash
bin/backup.py               # Backup upstream/ directory to S3
bin/requirements-update.sh  # Update Python dependencies
```

### CLI Options

```bash
itsup --help              # Show help for all commands
itsup --version           # Show version
itsup --verbose           # Enable DEBUG logging for any command
```

## V2 Architecture Patterns

### Project Structure

Configuration lives in `projects/`:

```
projects/
├── itsup.yml                # Infrastructure config (router IP, versions, backup S3 settings)
├── traefik.yml              # Traefik overrides (merged on top of generated config)
└── example-project/
    ├── docker-compose.yml   # Standard Docker Compose file
    └── ingress.yml          # Routing configuration (IngressV2 schema)
```

**Key files:**
- `itsup.yml` - Contains secrets as `${VAR}` placeholders (expanded at runtime from `secrets/itsup.txt`)
- `traefik.yml` - Custom Traefik overrides (plugins, log levels, etc.)
- `{project}/docker-compose.yml` - Service definitions (secrets as `${VAR}` placeholders)
- `{project}/ingress.yml` - Routing config (auto-generates Traefik labels)

### Secret Management

**Loading Order (later overrides earlier):**

1. `secrets/itsup.txt` - Shared secrets for all projects
2. `secrets/{project}.txt` - Project-specific secrets (optional)

**At Generation Time:**

- Secrets are LEFT as `${VAR}` placeholders in generated files
- Generated files are safe to backup/log (no actual secrets)

**At Deployment Time:**

- `itsup apply` loads secrets and passes them as environment variables
- `itsup run` loads secrets for infrastructure stacks (dns, proxy)
- `itsup proxy up` loads secrets for proxy stack
- Docker Compose expands `${VAR}` at runtime from the environment
- Each project gets itsup + project-specific secrets

**Important:**
- All docker compose commands that start containers MUST pass secrets via `env` parameter
- Use the helper function: `from lib.data import get_env_with_secrets`
- Format: `subprocess.run(cmd, env=get_env_with_secrets(project), check=True)`
- For infrastructure stacks (no project): `subprocess.run(cmd, env=get_env_with_secrets(), check=True)`
- This ensures ${VAR} placeholders in compose files are expanded correctly

### Template Generation

Minimal Jinja2 templates generate base configs:

- `tpl/proxy/traefik.yml.j2` - Minimal Traefik base (entryPoints, providers, trustedIPs)
- `tpl/proxy/docker-compose.yml.j2` - Proxy stack (Traefik, DNS, dockerproxy, optional CrowdSec)

**Override Flow:**

1. Generate minimal base from template
2. Deep merge `projects/traefik.yml` (user overrides) on top
3. Result: base + user customizations

### Label Injection

Traefik labels are auto-generated from `ingress.yml`:

```python
# projects/example-project/ingress.yml
enabled: true
ingress:
  - service: web
    domain: my-app.example.com
    port: 3000
    router: http

# Generated labels in upstream/example-project/docker-compose.yml:
labels:
  - traefik.enable=true
  - traefik.http.routers.example-project-web.rule=Host(`my-app.example.com`)
  - traefik.http.routers.example-project-web.tls.certresolver=letsencrypt
  - traefik.http.services.example-project-web.loadbalancer.server.port=3000
```

## Code Standards

See `@~/.claude/docs/development/coding-directives.md`

## Testing

See `~/.claude/docs/development/testing-directives.md`

- Framework: Python `unittest`
- Naming: `*_test.py` files
- Run: `bin/test.sh`
- Key test files:
  - `lib/data_test.py`: Database operations
  - `lib/upstream_test.py`: Upstream generation
  - `bin/backup_test.py`: Backup functionality
