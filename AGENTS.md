# AGENTS.md

Developer playbook for this repo. Read `README.md` first for architecture, components, and workflows.

## Non-Negotiables

- Work from the project root. Do not `cd` into subdirectories and stay there; use relative paths (e.g., `upstream/instrukt-ai/docker-compose.yml`) or `(cd dir && command)`.
- Match the pre-commit workflow exactly: `bin/format.sh` → `bin/lint.sh` → `bin/test.sh`. Run `bin/format.sh` before committing to avoid format churn.
- Python naming: public API has no leading underscore; internal/stateful attributes and helpers use a single leading underscore. Be consistent within each class.
- Do not containerize the itsUP codebase (Python code, CLI, API). Traefik runs on the host for zero-downtime deployments. Only upstream project services are containerized.
- Never touch the OpenSnitch database at `/var/lib/opensnitch/opensnitch.sqlite3` beyond read-only SELECTs. Do not move, copy, or modify it; treat it as a permanent audit log.

## Setup

```bash
make install          # Creates .venv, installs dependencies
source env.sh         # Activates venv, adds bin/ to PATH, enables completion
itsup init            # Clone/setup projects/ and secrets/ repos, copy samples (idempotent)
```

`source env.sh` can be added to your shell rc to keep PATH/venv/completion active.

`itsup init` prompts for git URLs (projects/, secrets/) and copies samples without overwriting existing files:
- `samples/env` → `.env`
- `samples/itsup.yml` → `projects/itsup.yml`
- `samples/traefik.yml` → `projects/traefik.yml`
- `samples/example-project/` → `projects/example-project/`
- `samples/secrets/itsup.txt` → `secrets/itsup.txt`

## Common Commands

```bash
bin/format.sh         # isort + black on api/ and lib/
bin/lint.sh           # pylint + mypy
bin/test.sh           # Run all *_test.py files
itsup apply           # Regenerate all artifacts + deploy
itsup apply <proj>    # Regenerate single project + deploy
itsup validate        # Validate all project configs (or pass project name)
```

Always test after changes.

## Stack Operations

Orchestrated runs:
```bash
itsup run             # dns → proxy → api → monitor (report-only)
itsup down            # full shutdown (monitor → api → all projects → proxy → dns)
itsup down --clean    # shutdown + remove stopped itsUP containers
```

Stack-specific:
```bash
itsup dns up|down|restart|logs
itsup proxy up|down|restart|logs [traefik]
```

Directory to command mapping:
- `dns/docker-compose.yml` → `itsup dns`
- `proxy/docker-compose.yml` → `itsup proxy`
- `upstream/project/` → `itsup svc project`

## Project Service Operations

```bash
itsup svc <project> <cmd> [service]
itsup svc <project> up             # start all services
itsup svc <project> up <service>   # start one service
itsup svc <project> down           # stop all services
itsup svc <project> restart        # restart all services
itsup svc <project> logs -f        # tail all services
itsup svc <project> logs -f <svc>  # tail specific service
itsup svc <project> exec <svc> sh  # shell inside a service container
```

Tab completion covers project names, compose commands, and service names.

## Monitor

```bash
itsup monitor start                  # full protection
itsup monitor start --report-only    # detection only
itsup monitor start --use-opensnitch # with OpenSnitch
itsup monitor stop                   # stop monitor
itsup monitor logs                   # tail monitor logs
itsup monitor cleanup                # review/cleanup blacklist
itsup monitor report                 # threat intel report
```

## Make Targets (dev workflow)

```bash
make help
make install
make test
make lint
make format
make clean
```

Runtime operations use `itsup`, not Make.

## Artifact Generation Helpers

```bash
itsup apply                # regen + deploy everything
itsup apply <project>      # regen + deploy single project
bin/write_artifacts.py     # regen proxy and upstream configs without deploying
```

## Utilities

```bash
bin/backup.py              # Backup upstream/ to S3
bin/requirements-update.sh # Update Python dependencies
itsup --help               # Global help
itsup --version            # Version
itsup --verbose            # Enable DEBUG logging for any command
```

## Architecture Notes (v2)

Project structure in `projects/`:
```
projects/
├── itsup.yml              # Infrastructure config with ${VAR} placeholders
├── traefik.yml            # Traefik overrides
└── example-project/
    ├── docker-compose.yml # Service definitions (secrets as ${VAR})
    └── ingress.yml        # Routing configuration (IngressV2 schema)
```

Secrets loading order (later overrides earlier):
1. `secrets/itsup.txt`
2. `secrets/{project}.txt` (optional)

Secrets stay as `${VAR}` in generated files. At deploy time, `itsup apply/run` loads secrets into the environment so docker compose can expand them. Use `get_env_with_secrets(project)` (from `lib.data`) when invoking compose commands:

```python
subprocess.run(cmd, env=get_env_with_secrets(project), check=True)
# For infrastructure stacks (no project):
subprocess.run(cmd, env=get_env_with_secrets(), check=True)
```

Templates:
- `tpl/proxy/traefik.yml.j2` and `tpl/proxy/docker-compose.yml.j2` generate minimal bases.
- Merge `projects/traefik.yml` on top for overrides.

Label injection: `ingress.yml` drives Traefik labels automatically (router rules, TLS, service ports).

## Testing

- Framework: Python `unittest`
- Naming: `*_test.py`
- Run: `bin/test.sh`
- Key suites: `lib/data_test.py`, `lib/upstream_test.py`, `bin/backup_test.py`
