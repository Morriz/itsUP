---
description: Acceptance scenario for the CLI schema-version guard at the validate
  boundary — a config-reading command resolves its version files under the install
  root and proceeds when the config schema matches the running app version.
delivered_by:
  - fix-tests-functional-commands-test-validate
---

# Schema Version Guard — Spec

## What it is

Config-reading commands (`apply`, `run`, `validate`, `pull`, `svc`, `create`)
open with the blocking schema-version check: `guard_schema_version()`
(`commands/common.py`) compares the config `schemaVersion` under the install
root against the running app version and refuses to run outdated config. The
version sources and blocking semantics are specified in
`project/spec/schema-migration`; this spec pins the guard's pass-through
behavior at the `validate` boundary so a regression in version-file resolution
is caught by the functional suite.

The business value is that the guard reads real version state from the install
root (`ITSUP_ROOT`) — an install tree whose schema matches the app version
passes the guard silently, and the command's own work proceeds.

### Use cases

The scenario below is bound by exactly one functional test in
`tests/functional/commands/test_validate.py`, which invokes the `validate`
command through the CLI runner against a per-test install root.

#### UC-SVG1: A schema-matched install root passes the guard and validates projects

```gherkin
Given an install root whose version files satisfy the schema-version check
And a projects directory containing one valid project
When itsup validate runs against that install root
Then the command exits 0
And the output reports all projects valid
```

## Canonical fields

The scenario exercises the in-process command chain
`commands/validate.py:validate` → `commands/common.py:guard_schema_version` →
`lib/version_check.py:check_schema_version`:

- **Inputs** — an `ITSUP_ROOT` install tree holding the version sources the
  guard reads (`pyproject.toml` for the app version; `projects/itsup.yml`
  `schemaVersion`, defaulting per `project/spec/schema-migration` when absent)
  plus one valid project directory.
- **Output** — exit code `0` and the all-projects-valid report on stdout; no
  schema-version error or warning is emitted.
