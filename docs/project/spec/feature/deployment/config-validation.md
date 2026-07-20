---
description: Acceptance scenarios for itsUP's pre-deploy configuration validation
  — the fail-closed gate that rejects project configuration Docker Compose itself
  would refuse, before invalid desired state is committed or reaches the deployment
  host.
---

# Config Validation — Spec

## What it is

`itsup validate [project]` is the operator-facing configuration gate, and
`validate_all()` is the same gate run fail-closed before any artifact write or
deploy (`project/spec/cli`, `project/spec/project-config`). Its business value
is catching invalid desired state at authoring time — on any machine, without
starting containers — instead of at deploy time on the host, where a rejected
compose file aborts a rollout.

For a container project the gate covers the project's `docker-compose.yml` with
Docker Compose's own schema/semantic validation, so a file that is well-formed
YAML but not a valid Compose document is rejected with the Compose error, not
reported as valid.

### Use cases

#### UC-CV1: A YAML-valid but Compose-invalid compose file is rejected by validate

```gherkin
Given a container project whose docker-compose.yml is well-formed YAML
And the document violates the Compose schema (a healthcheck.test list entry that YAML parses as a mapping instead of a string)
When itsup validate runs for that project
Then the command exits nonzero
And the reported errors surface the Compose schema violation
```

## Canonical fields

The gate's command surface, exit codes, and the itsUP-layer validation rules it
composes with are specified in `project/spec/cli` and
`project/spec/project-config`; this spec pins the acceptance scenarios only.

## See Also

- docs/project/spec/cli.md
- docs/project/spec/project-config.md
