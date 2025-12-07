# Developer Guide (concise, complete)
Read `README.md` first for architecture, components, and workflows.

## Critical Rules
- Always operate from repo root; never stay `cd`'d in subdirs. Use `(cd dir && command)` with relative paths.
- This repo itself is **not** containerized (Python CLI/API/monitoring/dns/proxy code). Only upstream project services are containerized. Do not containerize itsUP code.
- Never modify/move OpenSnitch DB `/var/lib/opensnitch/opensnitch.sqlite3`; read-only SELECTs only. No mv/cp/rm; handle via whitelist/iptables instead.

## Formatting, Linting, Tests (pre-commit order)
- Pre-commit runs: `bin/format.sh` → `bin/lint.sh` → `bin/test.sh`.
- Run `bin/format.sh` before committing to avoid formatting loops.
- Commands:
  - `bin/format.sh` (isort + black on api/ and lib/)
  - `bin/lint.sh` (pylint + mypy)
  - `bin/test.sh` (all `*_test.py`)

## Python Naming
- Public API: no leading underscore.
- Internal/private: single leading underscore on instance vars/methods. Be consistent.

## Setup & Installation
1) `make install` (creates .venv, installs deps).  
2) `source env.sh` (activates venv, adds `bin/` to PATH, enables completion). Add to shell rc if desired.  
3) `itsup init` (clones projects/secrets if needed; copies samples: `samples/env`→`.env`, `samples/itsup.yml`→`projects/itsup.yml`, `samples/traefik.yml`→`projects/traefik.yml`, `samples/example-project/`→`projects/example-project/`, `samples/secrets/itsup.txt`→`secrets/itsup.txt`). Idempotent.

## Deploy / Orchestration
- `itsup apply` (all configs regen + deploy in parallel; hash-based change detection); `itsup apply <project>` (single).
- `itsup run` (orchestrated startup dns→proxy→api→monitor, monitor report-only).
- `itsup down` (orchestrated shutdown monitor→api→ALL projects→proxy→dns); `itsup down --clean` also removes stopped itsUP containers.

## Stack Commands
- DNS stack (`dns/docker-compose.yml`): `itsup dns up|down|restart|logs`.
- Proxy stack (`proxy/docker-compose.yml`): `itsup proxy up [traefik] | down | restart | logs [traefik]`.
- Monitor: `itsup monitor start [--report-only|--use-opensnitch] | stop | logs | cleanup | report`.

## Project Service Ops
- Pattern: `itsup svc <project> <cmd> [service]`
  - `up` (all or specific service), `down`, `restart`, `logs -f [svc]`, `exec <svc> sh`.
- Tab completion covers projects, compose commands, services.

## Make (dev tools only; runtime uses itsup)
- `make help | install | test | lint | format | clean`.

## Artifact Generation
- `itsup apply` (all or single project).
- `bin/write_artifacts.py` (regen proxy & upstream configs without deploy).

## Utilities
- `bin/backup.py` (backup `upstream/` to S3)
- `bin/requirements-update.sh` (update Python deps)
- CLI: `itsup --help | --version | --verbose`

## Testing (always test after changes!)
- `bin/test.sh` (all Python unit tests `*_test.py`)
- `bin/lint.sh`, `bin/format.sh` as above
- Key suites: `lib/data_test.py`, `lib/upstream_test.py`, `bin/backup_test.py`

## V2 Architecture Patterns
- Structure:
  ```
  projects/
    itsup.yml              # infra config with ${VAR}
    traefik.yml            # overrides merged onto template output
    example-project/
      docker-compose.yml   # services with ${VAR} secrets
      ingress.yml          # IngressV2 routing config
  ```
- Secrets loading order (later overrides earlier): 1) `secrets/itsup.txt` 2) `secrets/{project}.txt` (optional).
- Secrets remain `${VAR}` in generated files; at deploy time `itsup apply/run` loads env so compose expands.
- Always start compose via `get_env_with_secrets(project)` from `lib.data`:
  ```python
  subprocess.run(cmd, env=get_env_with_secrets(project), check=True)
  # infra stacks (no project):
  subprocess.run(cmd, env=get_env_with_secrets(), check=True)
  ```
- Templates: `tpl/proxy/traefik.yml.j2` and `tpl/proxy/docker-compose.yml.j2` produce minimal bases; merged with `projects/traefik.yml`.
- Label injection: `ingress.yml` auto-generates Traefik labels (router rules, TLS, service ports).

## Containerization Scope
- Containerized: upstream project services only.
- Not containerized: dns honeypot mgmt code, proxy/Traefik config code, API server (`bin/start-api.sh`), CLI `itsup`, monitoring scripts.

## Code Standards
- See `@~/.claude/docs/development/coding-directives.md`

## Testing Standards
- See `~/.claude/docs/development/testing-directives.md`
