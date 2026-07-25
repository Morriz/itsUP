---
delivered_by: [main-red-blocks-deploy-two-clusters]
description: Acceptance scenario for the secrets commands' missing-target refusal — decrypt, encrypt, and diff-secrets resolve their target under the install root and, when the secrets directory or a named secret file is absent, refuse without side effects and report the missing target as a path usable from the caller's current directory.
---
# Secrets Target Resolution — Spec

## What it is

The `itsup decrypt`, `itsup encrypt`, and `itsup diff-secrets` commands operate
on a target under the install root: the `secrets/` directory, or a named secret
file within it. Before doing any cryptographic or diff work, each command
resolves that target and refuses when it is absent — a missing `secrets/`
directory, or a named file that does not exist — exiting non-zero without
loading keys, decrypting, encrypting, or writing anything.

The refusal names the missing target through the shared location renderer
(`lib/paths.py` `display_path`), so the reported path is usable from the
operator's current directory: relative to the install root when the caller
stands in it, absolute otherwise. A literal install-root-relative path in the
message would be correct only from one directory, and the CLI is installed
globally (`project/spec/cli`).

The business value is that an operator who runs a secrets command in the wrong
place, or names a file that is not there, gets an actionable refusal — the exact
missing path, resolvable from where they are — instead of a crash or a
misleading relative string, and no partial secret operation is performed.

### Use cases

The scenario below is bound by the functional tests in
`tests/functional/commands/test_decrypt.py`, `test_encrypt.py`, and
`test_diff_secrets.py`, which invoke the real Click commands against a per-test
install root with no target present.

#### UC-STR1: A secrets command refuses with a caller-portable path when its target is absent

```gherkin
Given the install root has no secrets directory, or a named secret file that does not exist
When an operator runs decrypt, encrypt, or diff-secrets against that target from outside the install root
Then the command exits non-zero without loading keys or performing any secret operation
And the refusal reports the missing target as a path usable from the operator's current directory
```

## Canonical fields

- **Inputs** — the invoked secrets command (`decrypt`, `encrypt`,
  `diff-secrets`) and the resolved install root (`ITSUP_ROOT`); the target is
  either the `secrets/` directory or a named secret file under it.
- **Output** — a non-zero exit and a refusal message naming the missing target;
  no key load, no decrypt/encrypt, no diff, and no file written. The reported
  path is absolute when the caller's current directory is not the install root,
  and install-root-relative when it is (`display_path`).

## Known caveats

- The portable-path rendering is the shared `display_path` contract, not a
  per-command behavior; every location a secrets command prints goes through it
  (`project/spec/cli`). A message that embeds a literal install-root-relative
  path is a defect, because it is correct only from the install root.
