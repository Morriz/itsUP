# CLI Reference

Complete reference for the `itsup` command-line interface.

## Global Options

```bash
itsup [OPTIONS] COMMAND [ARGS]
```

**Options**:
- `-h`, `--help`: Show help message and exit
- `-V`, `--version`: Show version and exit
- `-v`, `--verbose`: Verbosity count — `-v` = DEBUG, `-vv` = TRACE (the CLI ignores the `LOG_LEVEL` env var)

**Examples**:
```bash
itsup --help              # Show all commands
itsup -V                  # Show version
itsup -v apply            # Deploy with DEBUG output
itsup -vv apply           # Deploy with TRACE output
```

## Infrastructure Commands

### `itsup run`

Start complete infrastructure stack (orchestrated).

**Usage**:
```bash
itsup run
```

**What it does**:
1. Start DNS stack (creates proxynet network)
2. Start Proxy stack (Traefik + socket proxy)
3. Start API (host process)
4. Start Monitor in report-only mode (host process)

**Order**: Respects dependency order (dns → proxy → api → monitor).

**Monitor Mode**: Starts monitor in report-only mode (detection without blocking). For full protection with active blocking, use `itsup monitor start` after infrastructure is running.

**Example**:
```bash
itsup run
# Output:
# ✓ DNS stack started
# ✓ Proxy stack started
# ✓ API started
# ✓ Monitor started in report-only mode
```

### `itsup down`

Stop everything (orchestrated).

**Usage**:
```bash
itsup down [OPTIONS]
```

**Options**:
- `--clean`: Also remove stopped itsUP containers

**What it does**:
1. Stop Monitor
2. Stop API
3. Stop all project services (in parallel)
4. Stop Proxy stack
5. Stop DNS stack
6. Optionally: Remove stopped containers (if `--clean`)

**Examples**:
```bash
itsup down              # Stop everything
itsup down --clean      # Stop + cleanup containers
```

### `itsup init`

Initialize configuration (first-time setup).

**Usage**:
```bash
itsup init
```

**What it does**:
1. Prompt for git URLs (if projects/ or secrets/ not present)
2. Clone projects/ repository
3. Clone secrets/ repository
4. Copy sample files (if not already present):
   - `samples/env` → `.env`
   - `samples/itsup.yml` → `projects/itsup.yml`
   - `samples/traefik.yml` → `projects/traefik.yml`
   - `samples/example-project/` → `projects/example-project/`
   - `samples/secrets/itsup.txt` → `secrets/itsup.txt`

**Idempotent**: Can be run multiple times safely (won't overwrite existing files).

**Example**:
```bash
itsup init
# Prompts:
# Enter projects git URL: git@github.com:user/projects.git
# Enter secrets git URL: git@github.com:user/secrets.git
# ✓ Cloned projects/
# ✓ Cloned secrets/
# ✓ Copied sample files
```

## Stack Commands

### DNS Stack

**Usage**:
```bash
itsup dns COMMAND [SERVICE]
```

**Commands**:
- `up [service]`: Start DNS stack or specific service
- `down [service]`: Stop DNS stack or specific service
- `restart [service]`: Restart DNS stack or specific service
- `logs [service]`: Tail logs (optionally for specific service)

**Examples**:
```bash
itsup dns up              # Start DNS stack
itsup dns down            # Stop DNS stack
itsup dns restart         # Restart DNS stack
itsup dns logs            # Tail all DNS logs
```

### Proxy Stack

**Usage**:
```bash
itsup proxy COMMAND [SERVICE]
```

**Services**: `traefik`, `socket proxy`, `crowdsec` (if enabled)

**Commands**:
- `up [service]`: Start proxy stack or specific service
- `down [service]`: Stop proxy stack or specific service
- `restart [service]`: Restart proxy stack or specific service
- `logs [service]`: Tail logs (optionally for specific service)

**Examples**:
```bash
itsup proxy up                 # Start proxy stack
itsup proxy up traefik         # Start only Traefik
itsup proxy down               # Stop proxy stack
itsup proxy restart traefik    # Restart only Traefik
itsup proxy logs               # Tail all proxy logs
itsup proxy logs traefik       # Tail Traefik logs only
```

## Project Commands

### `itsup apply`

Deploy project configuration.

**Usage**:
```bash
itsup apply [PROJECT]
```

**Arguments**:
- `PROJECT` (optional): Project name (deploy specific project)

**What it does**:
- Runs `validate_all()` first and **refuses to deploy if any project is invalid** (global fail-closed gate — one bad project or a cross-project IP collision blocks the whole apply)
- If no `PROJECT`: Deploys `dns`, then `proxy`, then all projects in **topological egress-dependency order** (`list_projects_topo`), **sequentially**
- If `PROJECT` specified: Deploys that single target — valid targets are `dns`, `proxy`, or any project name
- A project with `enabled: false` in its `itsup-project.yml` is **stopped** (containers brought down) rather than deployed

**Smart Rollout**:
- Change detection runs `docker compose config --hash <service>` on the **generated** `upstream/<project>/docker-compose.yml` and compares to the running container's `com.docker.compose.config-hash` label (per-service; computed by Docker, not an MD5 over source files)
- Stateless services (those without volumes; plus `traefik`) get a zero-downtime rollout via the `docker rollout` plugin; stateful services restart normally via `docker compose up -d`
- Rollout is skipped when the service is unchanged or was not already running (first-time deploy)

**Examples**:
```bash
itsup apply                   # Deploy dns + proxy + all projects (sequential, topo order)
itsup apply dns               # Deploy DNS stack
itsup apply proxy             # Deploy proxy stack
itsup apply my-app            # Deploy single project
itsup -v apply                # Deploy with DEBUG output
```

**Output**:
```
✓ project-a deployed (config changed)
○ project-b skipped (no changes)
✗ project-c failed (docker error)
```

### `itsup svc`

Manage project services (docker compose operations).

**Usage**:
```bash
itsup svc PROJECT COMMAND [SERVICE] [OPTIONS]
```

**Arguments**:
- `PROJECT`: Project name (required)
- `COMMAND`: Docker Compose command (required)
- `SERVICE`: Service name (optional)

**Common Commands**:
- `up [service]`: Start services
- `down [service]`: Stop services
- `restart [service]`: Restart services
- `logs [service]`: View logs
- `ps`: List services
- `exec SERVICE CMD`: Execute command in service

**Examples**:
```bash
itsup svc my-app up              # Start all services
itsup svc my-app up web          # Start web service only
itsup svc my-app down            # Stop all services
itsup svc my-app restart         # Restart all services
itsup svc my-app logs -f         # Follow logs (all services)
itsup svc my-app logs -f web     # Follow web service logs
itsup svc my-app ps              # List services
itsup svc my-app exec web sh     # Shell into web service
```

**Tab Completion**: Project names, commands, and service names support tab completion.

### `itsup validate`

Validate project configuration.

**Usage**:
```bash
itsup validate [PROJECT]
```

**Arguments**:
- `PROJECT` (optional): Project name (validate specific project)

**What it does**:
- Loads each project's `docker-compose.yml` + `itsup-project.yml`
- Validates that ingress rows reference services that exist in compose
- Validates static `ipv4_address` declarations (within the proxynet subnet, not reserved, no conflicts) and detects cross-project IP collisions
- Validates `egress` targets point at an existing `project:service`
- For host-only projects (no compose), requires a `host` field

**Examples**:
```bash
itsup validate              # Validate all projects
itsup validate my-app       # Validate single project
```

## Monitor Commands

### `itsup monitor start`

Start container security monitor.

**Usage**:
```bash
itsup monitor start [OPTIONS]
```

**Options**:
- `--report-only`: Detection only, no blocking
- `--use-opensnitch`: Enable OpenSnitch integration

**Examples**:
```bash
itsup monitor start                     # Full protection mode
itsup monitor start --report-only       # Detection only
itsup monitor start --use-opensnitch    # With OpenSnitch
```

### `itsup monitor stop`

Stop container security monitor.

**Usage**:
```bash
itsup monitor stop
```

### `itsup monitor logs`

View monitor logs.

**Usage**:
```bash
itsup monitor logs
```

**Output**: Tails `logs/monitor.log` (follow mode).

### `itsup monitor cleanup`

Review and cleanup blacklist (interactive).

**Usage**:
```bash
itsup monitor cleanup
```

**What it does**:
1. Shows each blacklist entry
2. Prompts to keep or remove
3. Updates blacklist file
4. Removes corresponding iptables rules

**Example**:
```bash
itsup monitor cleanup
# Output:
# Entry: 1.2.3.4 (Malicious connection attempt)
# Keep this entry? [y/n]: n
# ✓ Removed 1.2.3.4
```

### `itsup monitor clear-iptables`

Remove iptables rules created by the monitor without touching blacklist files.

**Usage**:
```bash
itsup monitor clear-iptables
```

### `itsup monitor report`

Generate threat intelligence report.

**Usage**:
```bash
itsup monitor report
```

**What it does**: Runs `bin/analyze_threats.py` to analyze threat actors and print a report. (No format/output options.)

## Secret Management

### `itsup encrypt`

Encrypt secrets file.

**Usage**:
```bash
itsup encrypt [NAME] [--delete] [--force]
```

**Arguments / options**:
- `NAME` (optional): Secret name (`itsup` for shared secrets, or a project name). If omitted, operates over the secrets set.
- `--delete`: Delete plaintext `.txt` files after encryption
- `--force`: Force re-encryption even if content is unchanged

**What it does**:
1. Reads `secrets/{name}.txt` (plaintext)
2. Encrypts with SOPS
3. Writes `secrets/{name}.enc.txt` (encrypted)

**Examples**:
```bash
itsup encrypt itsup            # Encrypt shared secrets
itsup encrypt my-app           # Encrypt project secrets
itsup encrypt my-app --delete  # Encrypt then remove plaintext
```

### `itsup decrypt`

Decrypt secrets file.

**Usage**:
```bash
itsup decrypt [NAME]
```

**Arguments**:
- `NAME` (optional): Secret name (`itsup` for shared secrets, or a project name).

**What it does**:
1. Reads `secrets/{name}.enc.txt` (encrypted)
2. Decrypts with SOPS
3. Writes `secrets/{name}.txt` (plaintext)

**Examples**:
```bash
itsup decrypt itsup        # Decrypt shared secrets
itsup decrypt my-app       # Decrypt project secrets
```

**Note**: Plaintext `.txt` files are gitignored (safe to decrypt).

### `itsup diff-secrets`

Show meaningful diffs of encrypted secrets (decrypts via SOPS for comparison).

**Usage**:
```bash
itsup diff-secrets [FILE1] [FILE2] [--summary]
```

- `--summary`: Show a summary instead of the full diff.

### `itsup edit-secret`

Edit an encrypted secret seamlessly (decrypt → edit → re-encrypt).

**Usage**:
```bash
itsup edit-secret NAME
```

- `NAME` (required): Secret name to edit.

### `itsup sops-key`

Generate or rotate the SOPS (age) encryption key.

**Usage**:
```bash
itsup sops-key [--rotate]
```

- `--rotate`: Rotate the existing key and re-encrypt all secrets.

## Utility Commands

### `itsup status`

Show git status for the `projects/` and `secrets/` repos.

**Usage**:
```bash
itsup status
```

**What it does**: Reports uncommitted changes in the `projects` and `secrets` git repositories (it does NOT report DNS/proxy/API/monitor runtime state).

### `itsup commit`

Commit and push changes to the `projects` and `secrets` repos.

**Usage**:
```bash
itsup commit [--force]
```

- The commit message is **auto-generated** (no message argument).
- Auto-encrypts plaintext secrets before committing; detects SOPS key rotation.
- `--force` / `-f`: Skip encryption prompts and commit as-is (push uses `--force-with-lease`).

### `itsup pull`

Pull changes from the `projects` and `secrets` repos (via `git pull --rebase`).

**Usage**:
```bash
itsup pull [--apply]
```

- `--apply` / `-a`: Run `itsup apply` after a successful pull.

### `itsup create`

Scaffold a new project under `projects/`.

**Usage**:
```bash
itsup create NAME
```

### `itsup migrate`

Migrate configuration schema to the latest version.

**Usage**:
```bash
itsup migrate [--dry-run] [--list]
```

- `--dry-run`: Show what would change without making changes.
- `--list`: Show which fixers would run.

### `itsup logs`

Follow log files with smart formatting.

**Usage**:
```bash
itsup logs [NAMES...] [-n LINES]
```

- `NAMES`: One or more log names (tab-completed from available logs).
- `-n`, `--lines`: Number of initial lines to show (default: 100).

## Shell Completion

### Enable Completion

**Bash**:
```bash
source env.sh  # Enables completion automatically
```

**Or manually**:
```bash
eval "$(_ITSUP_COMPLETE=bash_source itsup)"
```

**Zsh**:
```bash
source env.sh  # Enables completion automatically
```

**Or manually**:
```bash
eval "$(_ITSUP_COMPLETE=zsh_source itsup)"
```

### What Gets Completed

- **Commands**: All itsup subcommands
- **Options**: All command options (--help, --verbose, etc.)
- **Projects**: Project names from projects/ directory
- **Services**: Service names from docker-compose.yml
- **Stacks**: dns, proxy, api, monitor

**Examples**:
```bash
itsup <TAB>               # Shows: apply, svc, monitor, encrypt, ...
itsup svc <TAB>           # Shows: project names
itsup svc my-app <TAB>    # Shows: up, down, restart, logs, ...
itsup svc my-app up <TAB> # Shows: service names
```

## Environment Variables

The `itsup` CLI does not read configuration from environment variables. Verbosity is set only via the `-v`/`-vv` count flags; directory locations (`projects/`, `secrets/`, `upstream/`) are fixed relative to the repo root. See [Environment Variables Reference](./environment-variables.md) for the secrets/config variables consumed at deploy time.

## Exit Codes

- **0**: Success
- **1**: Failure (validation failed, target not found, command/deploy error, or a non-zero exit propagated from a child `docker`/`git` process)

```bash
itsup apply my-app
echo $?  # 0 = success, non-zero = failure
```

## Advanced Usage

### Chaining Commands

```bash
# Deploy and show status
itsup apply && itsup status

# Validate, deploy, check logs
itsup validate && itsup apply && itsup svc my-app logs -f
```

### Using with Watch

```bash
# Watch project logs
watch -n 1 "itsup svc my-app logs --tail 20"

# Watch status
watch -n 5 "itsup status"
```

### Scripting with itsup

```bash
#!/bin/bash
# deploy-all.sh

set -e  # Exit on error

echo "Validating configuration..."
itsup validate

echo "Deploying projects..."
itsup apply

echo "Checking status..."
itsup status

echo "All deployed successfully!"
```

### Integration with CI/CD

```bash
# .github/workflows/deploy.yml
- name: Deploy
  run: |
    source env.sh
    itsup validate
    itsup apply
    itsup status
```

## Getting Help

### Command Help

```bash
itsup --help              # Main help
itsup apply --help        # Command-specific help
itsup svc --help          # Subcommand help
```

### Verbose Output

```bash
itsup --verbose apply     # Shows detailed operations
```

**Use for**:
- Debugging failures
- Understanding what CLI is doing
- Reporting issues

### Reporting Issues

**Include**:
1. Command that failed
2. Full output (with `--verbose`)
3. Configuration files (redact secrets)
4. System info (`uname -a`, `docker --version`)

**Example**:
```bash
itsup --verbose apply my-app > debug.log 2>&1
# Attach debug.log to issue report
```
