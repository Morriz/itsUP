---
id: 'project/spec/secrets-management'
type: 'spec'
scope: 'project'
description: 'How itsUP stores, loads, and injects secrets — SOPS/age encrypted files, .enc.txt-over-.txt auto-detection, per-context (non-merged) loading, and ${VAR} passthrough expanded by Docker Compose at deploy.'
generated_by: 'telec-init'
generated_at: '2026-06-11 00:00:00+00:00'
---

# Secrets Management — Spec

## What it is

Secrets are `KEY=value` env files under `secrets/`, stored **encrypted** with
SOPS (age) for git, decrypted **to memory only** at load time (never written as
plaintext by the load path), and injected into Docker Compose as process env.
Values referenced in compose files stay as `${VAR}` placeholders all the way
through generation; **Docker Compose expands them at deploy** using the injected
env. itsUP never bakes secret values into generated artifacts.

## Canonical fields

### File organization

- `secrets/itsup.{enc.txt|txt}` — itsUP **infrastructure** secrets (DNS, proxy,
  API, backup; e.g. `TRAEFIK_ADMIN`).
- `secrets/{project}.{enc.txt|txt}` — **per-project** secrets, one file per
  project.
- `secrets/.sops.yaml` — SOPS `creation_rules` holding the age recipient public
  key(s); every SOPS call passes `--config secrets/.sops.yaml`
  (`lib/sops.py:80,121,164`).

### Encryption / decryption (`lib/sops.py`)

- **age-based SOPS.** `itsup sops-key` generates/rotates the age key and writes
  the recipient into `.sops.yaml` (`commands/sops_key.py`).
- **`encrypt_file`** skips re-encryption when the decrypted content already
  matches the plaintext (SHA256 compare), unless `force=True` — this keeps git
  hashes stable for unchanged secrets (`lib/sops.py:63-76`).
- **Decrypt-to-memory.** `decrypt_to_memory` / `load_encrypted_env` decrypt to
  stdout and parse `KEY=value` without writing plaintext to disk
  (`lib/sops.py:135-169,206-234`). `itsup decrypt` / `itsup edit-secret` are the
  surfaces that do touch disk for editing.

### Loading (`lib/data.py:load_secrets`, `:27-85`)

- **Per-file auto-detection:** try `{name}.enc.txt` (SOPS) first; fall back to
  plaintext `{name}.txt`. If plaintext is used under `PYTHON_ENV=production`, a
  warning is logged (`lib/data.py:54-71`).
- **Per-context, NOT merged.** `load_secrets(None)` loads **only** `itsup`;
  `load_secrets(project)` loads **only** that project's file
  (`lib/data.py:76-81`). A project does **not** inherit `itsup` infrastructure
  secrets — each project's file must be self-contained.
- **Env assembly.** `get_env_with_secrets(project)` returns
  `{**os.environ, **secrets}` (secrets override ambient env) and is passed as
  `env=` to every compose/rollout subprocess (`lib/data.py:88-105`).

### `${VAR}` passthrough

Generated files keep `${VAR}` literally (`lib/data.py:157,201`); Docker Compose
substitutes them at `up`/`rollout` time from the injected env. Missing variables
surface as Compose-time errors, not itsUP errors.

## Known caveats

- **No cross-file inheritance.** The per-context (non-merged) loading above is
  easy to misread as layered; it is not. (Prior docs claimed an
  `itsup → project` override order that the code does not implement.)
- **Plaintext `.txt` is development-only** — production should use `.enc.txt`;
  the load path warns otherwise.

## See Also

- docs/reference/environment-variables.md
- docs/development/configuration.md
- docs/project/design/deployment-orchestration.md
