# CLI Reference

Complete reference for the `itsup` command-line interface.

## Global Options

```bash
itsup [OPTIONS] COMMAND [ARGS]
```

**Options**:
- `--help`: Show help message and exit
- `--version`: Show version and exit
- `--verbose`, `-v`: Enable DEBUG logging (shows detailed operations)

**Examples**:
```bash
itsup --help              # Show all commands
itsup --version           # Show version
itsup --verbose apply     # Deploy with debug output
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
2. Start Proxy stack (Traefik + dockerproxy)
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

**Services**: `traefik`, `dockerproxy`, `crowdsec` (if enabled)

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
- If `PROJECT` specified: Deploy single project
- If no `PROJECT`: Deploy all projects in parallel

**Smart Rollout**:
- Calculates config hash (docker-compose.yml + ingress.yml)
- Compares with stored hash
- Only deploys if changed

**Examples**:
```bash
itsup apply                   # Deploy all projects (in parallel)
itsup apply my-app            # Deploy single project
itsup apply --verbose         # Deploy with debug output
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
- Validates YAML syntax (docker-compose.yml, ingress.yml)
- Checks for required fields
- Verifies network configuration
- Validates secrets placeholders

**Examples**:
```bash
itsup validate              # Validate all projects
itsup validate my-app       # Validate single project
```

**Output**:
```
✓ my-app: Valid
✗ other-app: Missing required field 'domain' in ingress.yml
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
itsup monitor report [OPTIONS]
```

**Options**:
- `--format`: Report format (text, json, html)
- `--output`: Output file (default: stdout)

**Examples**:
```bash
itsup monitor report                        # Text report to stdout
itsup monitor report --format json          # JSON report
itsup monitor report --output report.html   # HTML report to file
```

## Secret Management

### `itsup encrypt`

Encrypt secrets file.

**Usage**:
```bash
itsup encrypt PROJECT
```

**Arguments**:
- `PROJECT`: Project name (or "itsup" for shared secrets)

**What it does**:
1. Reads `secrets/{project}.txt` (plaintext)
2. Encrypts with SOPS
3. Writes `secrets/{project}.enc.txt` (encrypted)

**Examples**:
```bash
itsup encrypt itsup        # Encrypt shared secrets
itsup encrypt my-app       # Encrypt project secrets
```

### `itsup decrypt`

Decrypt secrets file.

**Usage**:
```bash
itsup decrypt PROJECT
```

**Arguments**:
- `PROJECT`: Project name (or "itsup" for shared secrets)

**What it does**:
1. Reads `secrets/{project}.enc.txt` (encrypted)
2. Decrypts with SOPS
3. Writes `secrets/{project}.txt` (plaintext)

**Examples**:
```bash
itsup decrypt itsup        # Decrypt shared secrets
itsup decrypt my-app       # Decrypt project secrets
```

**Note**: Plaintext `.txt` files are gitignored (safe to decrypt).

## Utility Commands

### `itsup list`

List all projects.

**Usage**:
```bash
itsup list [OPTIONS]
```

**Options**:
- `--enabled-only`: Show only enabled projects (ingress.yml has `enabled: true`)
- `--format`: Output format (text, json, yaml)

**Examples**:
```bash
itsup list                    # List all projects
itsup list --enabled-only     # List only enabled projects
itsup list --format json      # JSON output
```

### `itsup status`

Show infrastructure status.

**Usage**:
```bash
itsup status
```

**What it shows**:
- DNS stack status
- Proxy stack status
- API status
- Monitor status
- Project counts (total, enabled, running)

**Example**:
```bash
itsup status
# Output:
# DNS:     ✓ Running
# Proxy:   ✓ Running (Traefik v3.5.1)
# API:     ✓ Running (http://localhost:8080)
# Monitor: ✓ Running (protection mode)
# Projects: 15 total, 12 enabled, 10 running
```

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

### Used by CLI

**`ITSUP_VERBOSE`**: Enable verbose output (same as `--verbose`)
```bash
export ITSUP_VERBOSE=1
itsup apply  # Will show debug output
```

**`ITSUP_CONFIG_DIR`**: Override config directory (default: `./projects`)
```bash
export ITSUP_CONFIG_DIR=/path/to/projects
itsup apply
```

**`ITSUP_SECRETS_DIR`**: Override secrets directory (default: `./secrets`)
```bash
export ITSUP_SECRETS_DIR=/path/to/secrets
itsup decrypt itsup
```

## Exit Codes

**0**: Success

**1**: General error (invalid arguments, command failed)

**2**: Configuration error (invalid YAML, missing files)

**3**: Deployment error (docker compose failed)

**130**: User interrupt (Ctrl+C)

**Example**:
```bash
itsup apply my-app
echo $?  # 0 = success, non-zero = error
```

## Command Aliases (Future)

**Potential aliases for convenience**:
```bash
itsup a       # itsup apply
itsup s       # itsup status
itsup l       # itsup list
itsup v       # itsup validate
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
