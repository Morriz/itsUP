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

## Git / Commits

- Pre-commit hooks (format/lint/test) run automatically on commit.
- Commit messages must follow Commitizen/Conventional Commit style (hook enforced); use `cz commit` or write `type: message` manually.
- Keep changes small and focused; use feature branches for larger edits, then PR.

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

## Code Standards

See  `@~/.claude/docs/development/coding-directives.md`

## Testing

See `~/.claude/docs/development/testing-directives.md`

- Framework: Python `unittest`
- Naming: `*_test.py`
- Run: `bin/test.sh`
- Key suites: `lib/data_test.py`, `lib/upstream_test.py`, `bin/backup_test.py`
