---
description: 'Acceptance scenarios for deploy convergence verification — the applied-state receipt a successful apply records, the verify command that proves a pushed SHA converged on the host, and the unauthenticated API liveness probe the watchdogs and the reconcile workflow depend on.'
delivered_by:
  - verifiable-deploy-chain
---

# Convergence Verification — Spec

## What it is

A green delivery signal must provably mean "the host converged to the pushed
state", with zero human involvement. The business value is converting silent
failure into a visible red signal: a deploy chain whose links (VPN, SSH, API,
apply) can break invisibly is verified end-to-end by recording what the host
actually applied (the applied-state receipt), asserting it against what was
pushed (`itsup verify`), and probing the API's liveness (`GET /health`). The
receipt and verify contracts are specified in `project/spec/cli`; the operating
chain that exercises them (synchronous reconcile workflow, daily scheduled run,
failure notification, supervised API) is specified in
`project/spec/runtime-operations`. This spec pins the acceptance scenarios.

### Use cases

#### UC-DCV1: A successful apply records the applied-state receipt

```gherkin
Given a valid configuration on the container host
When itsup apply completes successfully
Then the applied-state receipt records the current SHAs of the itsUP checkout and the projects and secrets config repos
And the receipt carries the timestamp of the apply
```

#### UC-DCV2: verify confirms a converged SHA

```gherkin
Given an applied-state receipt whose recorded SHAs include SHA X
When itsup verify X runs
Then the command exits 0
```

#### UC-DCV3: verify fails on a SHA the host did not converge to

```gherkin
Given an applied-state receipt whose recorded SHAs do not include SHA Y, or no receipt at all
When itsup verify Y runs
Then the command exits nonzero
And the output shows the recorded state so the divergence is visible
```

#### UC-DCV4: The API liveness probe answers without credentials

```gherkin
Given the API server is running
When GET /health is requested without any credential
Then the response is 200
And the body carries no configuration, project, or secret data
```

#### UC-DCV5: verify confirms the last applied target

```gherkin
Given an applied-state receipt recorded by a successful apply of project P
When itsup verify --target P runs
Then the command exits 0
And when the receipt's applied target is not P, or no receipt exists, the command exits nonzero showing the recorded state
```

## Canonical fields

The receipt fields, verify exit codes, and probe endpoint are contract-specified
in `project/spec/cli` and `project/spec/api-surface`; this spec pins the
acceptance scenarios only.

## See Also

- docs/project/spec/cli.md
- docs/project/spec/api-surface.md
- docs/project/spec/runtime-operations.md
