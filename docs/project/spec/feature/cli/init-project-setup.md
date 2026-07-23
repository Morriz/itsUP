---
id: project/spec/feature/cli/init-project-setup
type: spec
domain: project
scope: project
description: Acceptance scenarios for itsup init — it runs only from a valid itsUP checkout, identified by the samples/projects/itsup.yml marker, and seeds a fresh install by mirroring the samples/ templates into projects/, secrets/, and .env without overwriting existing files.
delivered_by: [init-root-check-requires-deleted-launcher]
---
# Init Project Setup — Spec

## What it is

`itsup init` bootstraps a fresh itsUP installation. It resolves the install root
through `lib/paths.root()` (from `ITSUP_ROOT` or the package location,
cwd-independent), confirms the resolved root is a real itsUP checkout, and seeds
the configuration repos from the in-repo `samples/` templates.

The checkout is identified by the presence of `samples/projects/itsup.yml` — the
itsUP-specific infra-config template that init depends on. init seeds the install
by **mirroring** the `samples/` template subtrees: each entry under
`samples/projects/` becomes an entry under `projects/`, each entry under
`samples/secrets/` becomes an entry under `secrets/`, and `samples/.env` becomes
`.env` at the root. init derives what to copy from the tree itself, so the set of
seeded files tracks `samples/` with no hardcoded manifest.

This spec pins init's enforcement at the command boundary so that a misresolved
root, or a seed step that drifts from the `samples/` layout, is caught by the
functional suite.

The business value is that a fresh itsUP checkout initialises correctly and only
from a genuine checkout, the seeded config always matches the shipped templates,
and existing files are never destroyed by a re-run.

### Use cases

The scenarios below are bound by functional tests in
`tests/functional/commands/test_init.py`, which invoke the `init` command through
the CLI runner against a per-test install root.

#### UC-IPS1: A valid checkout initialises by mirroring the samples templates

```gherkin
Given a resolved install root whose samples/projects/itsup.yml is a regular file
And samples/.env and the samples/projects and samples/secrets template trees are present
When itsup init runs against that install root
Then it is permitted past the project-root check
And it seeds .env from samples/.env
And it seeds every samples/projects entry under projects/
And it seeds every samples/secrets entry under secrets/
```

#### UC-IPS2: init never overwrites an existing destination

```gherkin
Given a resolved install root that already contains a .env with operator content
When itsup init runs against that install root
Then the existing .env is left unchanged
```

#### UC-IPS3: init refuses a root that is not an itsUP checkout

```gherkin
Given a resolved install root with no samples/projects/itsup.yml marker file
When itsup init runs against that install root
Then it exits nonzero
And it reports that it must be run from the itsUP project root
```

## Canonical fields

The scenarios exercise the in-process command chain `commands/init.py:init` →
`commands/init.py:_validate_project_structure`, with the root resolved by
`lib/paths.root()`:

- **Inputs** — an `ITSUP_ROOT` install tree holding the marker
  `samples/projects/itsup.yml`, the `samples/.env` template, and the
  `samples/projects` / `samples/secrets` template trees.
- **Output** — a seeded `projects/`, `secrets/`, and `.env` mirroring the
  templates; existing destinations preserved; a nonzero exit with the
  project-root message when the marker is absent.
