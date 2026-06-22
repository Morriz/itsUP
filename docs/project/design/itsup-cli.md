---
id: 'project/design/itsup-cli'
type: 'design'
scope: 'project'
description: 'How the itsup CLI is distributed and invoked — a packaged console-script run with the venv interpreter intrinsically, resolving its install root from ITSUP_ROOT rather than cwd, exposed globally on PATH, so no caller sources env.sh at runtime.'
delivered_by:
  - itsup-cli-package
  - itsup-cli-install-desource
  - itsup-cli-deprecate-env
---

# itsUP CLI Distribution — Design

## Purpose

itsup is invokable as a single global command that always runs with the project
venv and works from any directory, so nothing — systemd units, the API
self-update, `start-api.sh`, interactive shells — has to `source env.sh` first.

This exists because the prior `bin/itsup` (`#!/usr/bin/env python3`) bound the
interpreter to whatever python was active, and read cwd-relative data paths, so
every caller had to activate the venv and stand in the repo root. A single
missed activation produced `ModuleNotFoundError`; a wrong cwd produced empty
project/secret reads. Three separable concerns are resolved independently:
interpreter binding, root resolution, and PATH exposure.

## Inputs/Outputs

**Inputs**

- The repository checkout and its `.venv` (the editable install lives in the
  repo, so the package and the data dirs share one tree).
- `ITSUP_ROOT` (optional environment variable) — the install root override.

**Outputs**

- A global `itsup` command on `PATH` (a symlink to the venv console-script).
- All data access (`projects/`, `secrets/`, `upstream/`, `tpl/`,
  `projects/itsup.yml`, …) resolved beneath `root()`.

**Governing code**

- Entry point: `pyproject.toml` `[project.scripts] itsup = "itsup.cli:main"`.
- Root resolution: `lib/paths.py:root()`.
- Install + PATH exposure + `ITSUP_ROOT` wiring: `bin/install.sh` (`make install`).

## Invariants

1. **The interpreter is intrinsic.** `itsup` runs with the venv python because
   pip bakes the venv interpreter into the console-script shebang at
   `pip install -e .` time. No `source`/`activate` precedes a correct run.
2. **Root is resolved, never cwd-derived.** `root()` returns
   `ITSUP_ROOT` when set, otherwise derives the repo root from the installed
   package location. Every data path is `root() / "…"`; no module reads a
   cwd-relative `Path("projects"|"secrets"|"upstream"|"tpl")`.
3. **`itsup` is global.** A symlink (`/usr/local/bin/itsup` →
   `<repo>/.venv/bin/itsup`) puts the self-contained console-script on `PATH`
   for any user and any cwd.
4. **Single-root, not cwd/project-aware.** itsup binds to one install root; it
   does not select a project from the current directory the way `telec` does.
   See `project/adr/0001-itsup-cli-single-root`.
5. **No runtime sourcing.** systemd units, `start-api.sh`, and the API
   self-update invoke `itsup` (or the venv python) directly with `ITSUP_ROOT`
   in the environment; `env.sh` is a developer convenience only.

## Primary flows

### Install (`make install`)

```mermaid
flowchart TD
    A[make install] --> B[pip install -e . into .venv]
    B --> C[.venv/bin/itsup console-script<br/>venv shebang baked in]
    C --> D[symlink /usr/local/bin/itsup → .venv/bin/itsup]
    A --> E[set ITSUP_ROOT in systemd unit + API env]
```

### Invocation

`itsup <cmd>` from any cwd → the global symlink → the venv console-script (right
interpreter) → `main()` → `root()` resolves data dirs from `ITSUP_ROOT` or the
package location. cwd is irrelevant.

### Self-update (`_handle_itsup_update`)

`git reset --hard origin/main` → `pip install -e .` (re-mints the console-script
on entry-point changes) + `pip install -r requirements-prod.txt` → deploy stacks
→ `itsup apply` → restart API. Every `itsup` call is the global command.

## Failure modes

- **`ITSUP_ROOT` unset on a non-editable install.** `root()` cannot derive a
  root from a site-packages location → it raises a clear configuration error
  rather than silently reading the wrong tree. The editable install is the
  supported topology; `ITSUP_ROOT` is the override for anything else.
- **Entry-point or package layout change without re-running `pip install -e .`.**
  The console-script goes stale. The install step and the self-update both run
  the editable install so a code update can never leave `itsup` pointing at a
  removed module.
- **Global symlink created before the venv/editable install exists.** Dangling
  symlink. `make install` orders the editable install before the symlink.
- **A caller still sourcing `env.sh` and relying on cwd.** Tolerated but
  unnecessary; the runtime path no longer depends on it.

## See Also

- docs/project/adr/0001-itsup-cli-single-root.md
- docs/project/design/deployment-orchestration.md
