---
id: third-party/uv/uv-migration
type: third-party
scope: project
description: uv facts for migrating itsUP off pip/requirements — native dependency declarations, sync/lock commands, GitHub Actions setup-uv, and Dependabot's uv ecosystem.
---

# uv — Migration Reference (pip → uv)

Curated from the official Astral uv and GitHub docs for the `itsup-adopt-uv`
work. itsUP keeps the setuptools build backend; uv is adopted only as the
dependency/environment manager.

## Native dependency declaration

- Runtime dependencies are declared in `[project.dependencies]` in
  `pyproject.toml`; extras are preserved in the requirement string
  (e.g. `uvicorn[standard]`).
- Development/tooling dependencies use PEP 735 `[dependency-groups]` (the `dev`
  group is installed by default by `uv sync`). This replaces the
  `[project.optional-dependencies]` `test` extra + `requirements-test.txt`.
- `uv.lock` is the committed, cross-platform resolution lockfile and the source
  of resolution truth. It is generated from `pyproject.toml` and committed.
- A project with a `[build-system]` is a *package*: `uv sync` installs the
  project itself (so a setuptools `[project.scripts]` console-script is minted
  into `.venv/bin/`).

## Environment / sync commands

- `uv sync` — create/update `.venv`, install from `uv.lock` (incl. the default
  `dev` group), install the project, and **prune** the venv to the lock.
- `uv sync --no-dev` — runtime-only install (excludes dependency groups); the
  uv equivalent of installing only runtime deps.
- `uv sync --locked` — sync and **fail** if `uv.lock` is out of date w.r.t.
  `pyproject.toml` (the CI-safe locked install).
- `uv lock` — (re)generate `uv.lock`. `uv lock --check` verifies the lock is
  up to date without writing (there is no `uv lock --locked`).
- `uv add <pkg>` / `uv lock --upgrade` — add a dependency / refresh pins; the
  uv replacements for the old `pip install --upgrade` + `pip freeze` workflow.
- `uv run <tool> ...` — run a project tool (pytest/mypy/pylint/black/isort)
  inside the project environment; no `source .venv/bin/activate` needed.

## GitHub Actions (setup-uv)

- Action: `astral-sh/setup-uv@v8.1.0` (Astral pins it by commit
  `08807647e7069bb48b6ef5acd8ec9567f424441b`).
- Enable dependency caching with `enable-cache: true`.
- The action can set the Python version via `with: python-version: <ver>`.
- Recommended CI shape: `uv sync --locked` (optionally `--all-extras --dev`)
  then `uv run pytest`.

## Dependabot

- Use `package-ecosystem: "uv"` in `.github/dependabot.yml` (not `"pip"`); it
  updates `uv.lock` / `pyproject.toml`.
- If uv's `exclude-newer` is used, set a matching Dependabot `cooldown`. Some
  uv Dependabot use cases are still maturing — track the upstream issue.

## Sources

- https://docs.astral.sh/uv/concepts/projects/dependencies/
- https://docs.astral.sh/uv/guides/integration/github/
- https://docs.astral.sh/uv/guides/integration/dependabot/
- https://docs.github.com/en/code-security/reference/supply-chain-security/supported-ecosystems-and-repositories
