---
description: 'How itsUP versions and migrates project configuration — schemaVersion in itsup.yml vs the app version, ordered fixers, the blocking pre-command check, and dry-run/list.'
---

# Schema Migration — Spec

## What it is

itsUP versions the **shape** of project configuration so the CLI and the
on-disk config stay compatible across upgrades. A `schemaVersion` stored in
`projects/itsup.yml` is compared against the running app version; when config is
behind, commands refuse to run until the operator runs `itsup migrate`, which
applies ordered **fixers** that rewrite config in place.

## Canonical fields

### Versions (`lib/migrations.py`)

- **Schema version** — `schemaVersion` in `projects/itsup.yml`, default `"1.0.0"`
  when absent (`get_schema_version`, `:10-23`).
- **App version** — `MAJOR.MINOR.0` derived from `pyproject.toml`
  (`get_app_version`, `:43-52`). Patch is ignored, so migrations key on
  minor-version bumps.

### The blocking check (`lib/version_check.py`)

`check_schema_version()` runs at the top of most commands (`apply`, `run`,
`validate`, `pull`, `svc`, `create`). If `schema < app` it logs an error and
**exits non-zero**, instructing the operator to run `itsup migrate`; if
`schema > app` it warns to upgrade itsUP. The check is automatic; the migration
itself is always explicit.

### `itsup migrate` (`commands/migrate.py` → `lib/migrations.py:migrate`)

- No-op when `schema >= app` (`:70-72`).
- Applies the ordered fixer list `FIXERS_V2_1` (`lib/fixers/__init__.py`); each
  fixer exposes `apply(projects_dir, dry_run)` returning
  `{renamed, skipped, errors}`. Any fixer error **aborts** the run
  (`:85-93`).
- On success (non-dry-run): bumps `schemaVersion` to the app version, then runs
  `validate_all()` and fails if any project is invalid (`:95-113`).
- `--dry-run` applies nothing; `--list` prints the pending fixers only.

### Fixers

Currently one: `rename_ingress` — renames `projects/{p}/ingress.yml` →
`itsup-project.yml`, preferring `git mv` when `projects/` is a git repo
(`lib/fixers/rename_ingress.py`).

## Known caveats

- **`bin/migrate_to_v2.py` is a separate one-shot tool**, not wired into
  `itsup migrate`. It performs the bulk V1→V2 reshape (`upstream/` + `db.yml` →
  `projects/` + `secrets/`) and is run standalone.
- The fixer list constant is named `FIXERS_V2_1`; new schema bumps add fixers to
  this ordered list.

## See Also

- docs/project/design/network-segmentation.md
