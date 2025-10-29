# Project Structure

Overview of the itsup codebase organization and key directories.

## Directory Layout

```
/home/morriz/srv/
├── api/                    # API server (FastAPI application)
├── bin/                    # Executable scripts
│   ├── itsup              # Main CLI entry point
│   ├── format.sh          # Code formatting (isort + black)
│   ├── lint.sh            # Linting (pylint + mypy)
│   ├── test.sh            # Run unit tests
│   ├── backup.py          # S3 backup script
│   └── write_artifacts.py # Artifact generation (without deployment)
├── commands/               # CLI command implementations
│   ├── apply.py           # Deployment command
│   ├── dns.py             # DNS stack management
│   ├── proxy.py           # Proxy stack management
│   ├── monitor.py         # Monitor commands
│   └── ...
├── config/                 # Runtime configuration
│   ├── monitor-whitelist.txt
│   └── monitor-blacklist.txt
├── dns/                    # DNS stack configuration
│   └── docker-compose.yml
├── docs/                   # Documentation (this folder)
│   ├── README.md
│   ├── architecture.md
│   ├── networking.md
│   ├── stacks/
│   ├── operations/
│   ├── development/
│   └── reference/
├── lib/                    # Core library modules
│   ├── data.py            # Configuration loading, templates
│   ├── deploy.py          # Deployment logic
│   ├── upstream.py        # Label injection, artifact generation
│   ├── *_test.py          # Unit tests
│   └── ...
├── logs/                   # Log files (gitignored)
│   ├── access.log         # Traefik access log
│   ├── api.log            # API log
│   └── monitor.log        # Monitor log
├── projects/               # Source configurations (independent git repo)
│   ├── itsup.yml          # Infrastructure config (secrets as ${VAR})
│   ├── traefik.yml        # Traefik overrides
│   └── {project}/
│       ├── docker-compose.yml  # Service definitions
│       └── ingress.yml    # Routing configuration
├── proxy/                  # Proxy stack
│   ├── docker-compose.yml # Proxy stack services
│   └── traefik/
│       ├── traefik.yml    # Generated Traefik config
│       ├── acme.json      # Let's Encrypt certificates
│       └── *.conf.yaml    # Dynamic configurations
├── samples/                # Sample configurations
│   ├── env                # Sample .env file
│   ├── itsup.yml          # Sample infrastructure config
│   ├── traefik.yml        # Sample Traefik overrides
│   ├── example-project/   # Sample project
│   └── secrets/
│       └── itsup.txt      # Sample secrets file
├── secrets/                # Encrypted secrets (independent git repo)
│   ├── itsup.txt          # Shared secrets (plaintext, gitignored)
│   ├── itsup.enc.txt      # Shared secrets (encrypted, in git)
│   ├── {project}.txt      # Project secrets (plaintext, gitignored)
│   └── {project}.enc.txt  # Project secrets (encrypted, in git)
├── tpl/                    # Jinja2 templates
│   └── proxy/
│       ├── traefik.yml.j2
│       └── docker-compose.yml.j2
├── upstream/               # Generated artifacts (gitignored)
│   └── {project}/
│       └── docker-compose.yml  # Generated with Traefik labels
├── .env                    # Environment variables (gitignored)
├── .venv/                  # Python virtual environment (gitignored)
├── CLAUDE.md               # Project instructions for AI assistants
├── Makefile                # Development commands
├── README.md               # Project overview
├── env.sh                  # Environment setup script
└── requirements.txt        # Python dependencies
```

## Key Directories

### `/api/` - API Server

**Purpose**: Web-based management interface (FastAPI).

**Structure** (example, actual may vary):

```
api/
├── main.py               # FastAPI app entry point
├── routes/
│   ├── projects.py       # Project management endpoints
│   ├── stacks.py         # Stack management endpoints
│   └── health.py         # Health check
├── models/
│   └── schemas.py        # Pydantic models
└── services/
    ├── docker.py         # Docker operations
    └── deploy.py         # Deployment logic
```

**Not Containerized**: Runs as host process for direct system access.

### `/bin/` - Executables

**Purpose**: Executable scripts and utilities.

**Key Files**:

- `itsup`: Main CLI entry point (Python script)
- `format.sh`: Formatting script (isort + black) - run before commit
- `lint.sh`: Linting script (pylint + mypy)
- `test.sh`: Run all unit tests (\*\_test.py)
- `backup.py`: S3 backup script (called by cron)
- `write_artifacts.py`: Regenerate artifacts WITHOUT deploying

**Path**: Add to PATH via `source env.sh` for easy access.

### `/commands/` - CLI Commands

**Purpose**: Implementation of each `itsup` subcommand.

**Pattern**: One file per command or command group.

**Example**:

```python
# commands/apply.py
import click
from lib.deploy import deploy_upstream_project

@click.command()
@click.argument('project', required=False)
def apply(project):
    """Deploy project configuration"""
    if project:
        deploy_upstream_project(project)
    else:
        # Deploy all projects
        deploy_all()
```

**Loaded by**: `bin/itsup` (CLI entry point dynamically loads commands).

### `/lib/` - Core Library

**Purpose**: Reusable modules for configuration, deployment, and utilities.

**Key Modules**:

**`data.py`**: Configuration loading and templates

- `load_project(project)`: Load docker-compose.yml + ingress.yml
- `get_env_with_secrets(project)`: Load secrets for deployment
- `get_trusted_ips()`: Build Traefik trustedIPs list
- `get_router_ip()`: Detect router IP from itsup.yml
- Template rendering (Jinja2)

**`deploy.py`**: Deployment logic

- `deploy_upstream_project(project, service)`: Deploy single project
- `deploy_all()`: Deploy all projects in parallel
- Smart rollout with change detection (config hash)

**`upstream.py`**: Label injection and artifact generation

- `inject_traefik_labels(compose, ingress, project)`: Generate Traefik labels
- `write_upstream(project)`: Generate upstream/docker-compose.yml

**Tests**: `*_test.py` files (unit tests using Python unittest).

### `/projects/` - Source Configurations

**Purpose**: Source of truth for all project configurations.

**Git**: An independent separate repo for configuration.

**Structure**:

```
projects/
├── itsup.yml              # Infrastructure config (router IP, versions, backup)
├── traefik.yml            # Traefik overrides (merged on top of generated config)
└── {project}/
    ├── docker-compose.yml # Standard Docker Compose file (secrets as ${VAR})
    └── ingress.yml        # IngressV2 schema (routing config)
```

**Important**:

- Secrets are `${VAR}` placeholders (expanded from secrets/ at runtime)
- This directory is edited directly (NOT upstream/)
- `itsup apply` reads from here to generate artifacts

### `/secrets/` - Encrypted Secrets

**Purpose**: Secure storage of sensitive environment variables.

**Git**: An independent separate repo for secrets.

**Structure**:

```
secrets/
├── itsup.txt              # Shared secrets (plaintext, gitignored)
├── itsup.enc.txt          # Shared secrets (encrypted, in git)
├── {project}.txt          # Project secrets (plaintext, gitignored)
└── {project}.enc.txt      # Project secrets (encrypted, in git)
```

**Workflow**:

1. Edit `.txt` file (plaintext)
2. Encrypt: `itsup encrypt {project}`
3. Commit `.enc.txt` file (safe to version control)
4. Decrypt on target: `itsup decrypt {project}`

**Loading Order**:

1. `secrets/itsup.txt` (shared)
2. `secrets/{project}.txt` (project-specific)

Later overrides earlier.

### `/upstream/` - Generated Artifacts

**Purpose**: Generated docker-compose.yml files with Traefik labels injected.

**Git**: Gitignored (regenerated from projects/).

**Structure**:

```
upstream/
└── {project}/
    └── docker-compose.yml  # Generated with Traefik labels
```

**Generation**: `bin/write_artifacts.py` or `itsup apply`.

**Important**:

- DO NOT edit these files manually (changes will be overwritten)
- NOT the source of truth (projects/ is)
- Used only for deployment

### `/proxy/` - Proxy Stack

**Purpose**: Traefik reverse proxy configuration and state.

**Structure**:

```
proxy/
├── docker-compose.yml      # Proxy stack services (Traefik, dockerproxy)
└── traefik/
    ├── traefik.yml         # Generated Traefik config (base + overrides)
    ├── acme.json           # Let's Encrypt certificates (600 perms)
    └── *.conf.yaml         # Dynamic configurations (e.g., api-log.conf.yaml)
```

**Generation**:

1. Base config from template (`tpl/proxy/traefik.yml.j2`)
2. Merged with user overrides (`projects/traefik.yml`)
3. Result written to `proxy/traefik/traefik.yml`

### `/tpl/` - Templates

**Purpose**: Jinja2 templates for generating base configurations.

**Key Templates**:

- `tpl/proxy/traefik.yml.j2`: Minimal Traefik base config
- `tpl/proxy/docker-compose.yml.j2`: Proxy stack compose file

**Usage**:

```python
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('tpl'))
template = env.get_template('proxy/traefik.yml.j2')
output = template.render(router_ip='192.168.1.1', trusted_ips=[...])
```

### `/logs/` - Log Files

**Purpose**: Persistent log storage with rotation.

**Files**:

- `access.log`: Traefik access log (HTTP requests)
- `api.log`: API server log
- `monitor.log`: Container security monitor log

**Rotation**: Managed by logrotate (`/etc/logrotate.d/itsup`).

**View**: `tail -f logs/*.log` or via CLI commands.

## Configuration Flow

### Project Configuration → Deployment

```
projects/{project}/
├── docker-compose.yml     (1) Source config with ${VAR} placeholders
└── ingress.yml            (2) Routing config

                ↓ bin/write_artifacts.py or itsup apply

upstream/{project}/
└── docker-compose.yml     (3) Generated with Traefik labels injected

                ↓ docker compose up -d (with secrets loaded)

Running Containers         (4) ${VAR} expanded from secrets/*.txt
```

### Secrets Flow

```
secrets/{project}.txt      (1) Edit plaintext secrets
        ↓ itsup encrypt
secrets/{project}.enc.txt  (2) Encrypted (safe for git)
        ↓ git commit && git push
Remote Repository          (3) Version controlled
        ↓ git clone/pull on target
secrets/{project}.enc.txt  (4) Encrypted file on target
        ↓ itsup decrypt
secrets/{project}.txt      (5) Decrypted on target
        ↓ itsup apply (loads secrets)
Environment Variables      (6) Passed to docker compose
        ↓ docker compose up
${VAR} Expansion           (7) Placeholders expanded in containers
```

## Code Organization Principles

### Separation of Concerns

**Configuration** (`projects/`):

- What to deploy (services, images, networks)
- How to route (domains, ports, protocols)

**Generation** (`lib/upstream.py`):

- Transform configuration into deployable artifacts
- Inject Traefik labels
- Merge templates with overrides

**Deployment** (`lib/deploy.py`):

- Execute docker compose operations
- Manage secrets loading
- Handle change detection

**CLI** (`commands/`):

- User interface for operations
- Argument parsing and validation
- Orchestration of library functions

### DRY (Don't Repeat Yourself)

**Avoid**:

- Duplicating docker-compose.yml for each project
- Manually writing Traefik labels (auto-generated from ingress.yml)
- Hard-coding values (use itsup.yml for configuration)

**Use**:

- Templates for base configurations
- Functions for repeated logic
- Configuration files for variable data

### Single Source of Truth

**Configuration**: `projects/` directory

- All service definitions
- All routing rules
- All infrastructure settings

**Secrets**: `secrets/` directory (encrypted)

- All environment variables
- All sensitive data

**Never**:

- Edit `upstream/` directly (generated)
- Store secrets in code or config (use secrets/)
- Hard-code infrastructure details (use itsup.yml)

## Testing Structure

### Unit Tests

**Location**: `lib/*_test.py`

**Pattern**: One test file per module (e.g., `data_test.py` tests `data.py`).

**Framework**: Python `unittest`

**Example**:

```python
# lib/data_test.py
import unittest
from lib.data import load_project

class TestLoadProject(unittest.TestCase):
    def test_load_project(self):
        compose, ingress = load_project('example-project')
        self.assertIsNotNone(compose)
        self.assertEqual(ingress['enabled'], True)
```

**Run**: `bin/test.sh` (runs all `*_test.py` files).

### Integration Tests

**Location**: TBD (future)

**Purpose**: Test full deployment workflows.

**Example**:

```bash
# Test full deployment
itsup apply test-project
curl https://test.example.com/health
itsup svc test-project down
```

## Development Workflow

### Making Changes

1. **Edit source** (`projects/` or code)
2. **Format**: `bin/format.sh`
3. **Lint**: `bin/lint.sh`
4. **Test**: `bin/test.sh`
5. **Commit**: `git commit`
6. **Deploy**: `itsup apply`

### Adding a New Project

1. Create `projects/{project}/` directory
2. Add `docker-compose.yml` (service definitions)
3. Add `ingress.yml` (routing config)
4. Optionally add `secrets/{project}.txt` (project secrets)
5. Encrypt secrets: `itsup encrypt {project}`
6. Deploy: `itsup apply {project}`

### Adding a New CLI Command

1. Create `commands/{command}.py`
2. Implement command using click decorators
3. CLI auto-discovers and loads new command
4. Test: `itsup {command} --help`

### Modifying Templates

1. Edit `tpl/proxy/*.j2`
2. Regenerate: `bin/write_artifacts.py`
3. Test: `itsup proxy restart`
4. Commit template changes

## Best Practices

### Code Style

- **PEP 8**: Follow Python style guide
- **Type Hints**: Use for function signatures
- **Docstrings**: Document all public functions
- **Underscore Naming**: `_private` for internal, public for API

### File Organization

- **Keep files focused**: One purpose per file
- **Logical grouping**: Related functions in same module
- **Clear naming**: File name should indicate purpose

### Configuration Management

- **Don't hard-code**: Use `itsup.yml` for settings
- **Use templates**: For base configs that need customization
- **Override pattern**: Base + overrides (e.g., Traefik config)

### Secret Handling

- **Never commit plaintext secrets**: Only `.enc.txt` in git
- **Use ${VAR} placeholders**: In compose files
- **Load at runtime**: Secrets expanded during deployment

### Testing

- **Test before commit**: Run `bin/test.sh`
- **Test deployments**: Verify changes on non-critical projects first
- **Validate configs**: Use `itsup validate` before deploying

## Future Structure Changes

**Potential Improvements**:

- `/tests/` directory (separate from lib/)
- `/plugins/` for extensibility
- `/schemas/` for YAML schema definitions
- Better separation of CLI and API code
