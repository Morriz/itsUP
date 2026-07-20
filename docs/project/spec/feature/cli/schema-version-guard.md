---
description: Acceptance scenario for the CLI schema-version guard at the validate
  boundary — a config-reading command resolves its version files under the install
  root and refuses to run when the config schema is older than the running app
  version.
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
`project/spec/schema-migration`; this spec pins the guard's enforcement at the
`validate` boundary so a bypassed, broken, or misresolved guard is caught by
the functional suite.

The business value is that the guard reads real version state from the install
root (`ITSUP_ROOT`) and blocks before the command's own work starts: outdated
config never reaches validation, artifact generation, or deployment.

### Use cases

The scenario below is bound by exactly one functional test in
`tests/cli/test_schema_version_guard.py`, which invokes the `validate` command
through the CLI runner against a per-test install root.

#### UC-SVG1: An outdated config schema blocks validate before project validation

```gherkin
Given an install root whose config schema version is older than the running app version
When itsup validate runs against that install root
Then the command exits nonzero
And the schema-version failure is reported as error output
```

## Canonical fields

The scenario exercises the in-process command chain
`commands/validate.py:validate` → `commands/common.py:guard_schema_version` →
`lib/version_check.py:check_schema_version`:

- **Inputs** — an `ITSUP_ROOT` install tree holding the version sources the
  guard reads: `pyproject.toml` (app version) and `projects/itsup.yml`
  `schemaVersion` (config schema version, defaulting per
  `project/spec/schema-migration` when absent), shaped so schema < app.
- **Output** — a nonzero exit code and non-empty error output; project
  validation does not run.
