---
description: 'appleboy/ssh-action facts the reconcile workflow depends on — envs transfer syntax, no fail-fast by default (script_stop removed; set -e required), and the 10m command_timeout default.'
---

# appleboy/ssh-action — Remote Script Contract

Curated from the official appleboy/ssh-action README (github.com/appleboy/ssh-action)
for the `verifiable-deploy-chain` work: the shared reconcile workflow runs its
deploy synchronously through this action's `script` input.

## Environment transfer (`envs`)

- `envs` is a comma-separated list of variable **names**; each named variable is
  read from the job's `env` context and exported into the remote script's
  environment: `env: {FOO: bar}` + `with: {envs: FOO}`.
- `GITHUB_*` variables are **not** transferred implicitly by `envs` — a separate
  `allenvs` input exists to pass all `GITHUB_`/`INPUT_`-prefixed variables.
  To pass a specific value (e.g. the pushed SHA), set it explicitly in the job
  `env` (`GITHUB_SHA: ${{ github.sha }}`) and name it in `envs`.
- `envs_format` exists for flexible transfer formatting; the default behavior
  above is sufficient for plain name transfer.

## Failure semantics (`script`)

- A failing command does **not** stop the remote script and does not by itself
  fail the action: the deprecated `script_stop` input was **removed**, and the
  documented replacement is `set -e` as the first line of the script.
- Without `set -e`, a multi-line script continues past failures and the step's
  outcome reflects only the final command — a synchronous deploy script MUST
  start with `set -e` for its exit status to be truthful.

## Timeout

- `command_timeout` defaults to **10m**; a full pull + apply (image pulls
  included) can exceed it, so the reconcile workflow sets it explicitly.

## Sources

- https://github.com/appleboy/ssh-action (README, v1.x)
