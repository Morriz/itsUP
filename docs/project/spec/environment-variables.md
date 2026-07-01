---
description: 'The environment variables and secrets itsUP actually reads — the per-context (non-merged) secret-loading model in lib/data.py, the few process env vars the CLI/API/library consume, and the ${VAR} placeholders that stay literal until Docker Compose expands them at deploy time.'
---

# Environment Variables — Spec

## What it is

itsUP distinguishes two value sources that the prose often conflates:

1. **Process environment variables** read directly by the Python CLI, API, or
   library at runtime (`os.environ` / `os.getenv`). There are only a handful.
2. **Secrets** loaded from `secrets/` files into a deploy-time environment that
   Docker Compose then uses to expand `${VAR}` placeholders.

### The secret-loading model (`lib/data.py`)

Secrets are loaded **per context, not merged** (`load_secrets`, `lib/data.py:34-92`):

- An **infrastructure operation** (proxy, DNS, API, backup — any call with no
  `project_name`) loads **only** `secrets/itsup.{enc.txt|txt}` (`:83-88`).
- A **project deploy** (`project_name` set) loads **only**
  `secrets/{project}.{enc.txt|txt}` (`:83-85`). A project does **not** inherit
  itsUP infrastructure secrets — a value a project needs must live in that
  project's own secrets file.
- For each file, the encrypted `.enc.txt` is tried first and the plaintext
  `.txt` is the fallback (`_load_secret_file`, `:59-80`). `.enc.txt` is decrypted
  via SOPS (`load_encrypted_env`); plaintext is read directly (`load_env_file`).

`get_env_with_secrets(project_name=None)` (`lib/data.py:95-112`) is the single
standard entry point for running `docker compose` with secrets present. Its
entire body is `return {**os.environ, **secrets}` — current process env overlaid
by the loaded secrets (secrets win on key collision). It performs **no
validation** of required variables.

Loaders that read `projects/*.yml` config (`load_project`, `load_itsup_config`,
`load_traefik_overrides`, `load_middleware_overrides`) leave `${VAR}`
placeholders **literal** — they are never expanded at load time (`lib/data.py:172,
458,469,489,509`). Expansion happens only when Docker Compose receives the env
built by `get_env_with_secrets` at `docker compose up`.

## Canonical fields

### Process environment variables (read by Python)

| Name | Required / default | Source (read site) | Consumer / purpose |
|------|--------------------|--------------------|--------------------|
| `ITSUP_ROOT` | optional; falls back to repo root derived from package location | `lib/paths.py:25` | Single source of truth for the install root used by every data path; fails closed if set to a missing dir or if derivation lands outside the repo tree (`lib/paths.py:26-39`). Also consumed by `bin/install-bringup.sh:17` and exported by `env.sh:6`. |
| `PYTHON_ENV` | optional; `api/main.py` defaults to `"development"` | `lib/data.py:76`; `api/main.py:45,154` | When `== "production"`: warns on plaintext-secret use during deploy (`lib/data.py:76-77`) and enables `proxy_headers` for the API server (`api/main.py:154`). |
| `LOG_LEVEL` | optional; default `INFO` | `lib/logging_config.py:123` | Default log level for non-CLI entrypoints (e.g. the API/library). The CLI ignores it and maps `-v`/`-vv` to DEBUG/TRACE instead (`itsup/cli.py:46-57`). |

Verbosity for the `itsup` CLI is a flag, not an env var: `--verbose/-v` (`count`)
on the CLI group (`itsup/cli.py:37-57`).

### Infrastructure secrets (`secrets/itsup.{enc.txt|txt}`)

Names verified against `samples/secrets/itsup.txt` and their code/template consumers.

| Name | Required / default | Consumer / purpose |
|------|--------------------|--------------------|
| `API_KEY` | required for the API | `lib/auth.py:22,32` — apikey guarding the management API; 503 if unset. |
| `LETSENCRYPT_EMAIL` | required by the proxy template | `tpl/traefik.yml.j2:20`; `tpl/docker-compose.yml.j2:59` (`${...:?}` — fails if empty) — ACME account email. |
| `CROWDSEC_APIKEY` | required by the proxy template | `tpl/docker-compose.yml.j2:56,84` (`${...:?}`) — CrowdSec bouncer key for Traefik. |
| `AWS_ACCESS_KEY_ID` | required for backup | `bin/backup.py:74,87` — S3 credentials for `bin/backup.py`. |
| `AWS_SECRET_ACCESS_KEY` | required for backup | `bin/backup.py:75,88`. |
| `AWS_S3_HOST` | required for backup | `bin/backup.py:76,89` — S3 endpoint host (https:// prefixed if scheme-less, `:96-99`). |
| `AWS_S3_REGION` | required for backup | `bin/backup.py:77,90`. |
| `AWS_S3_BUCKET` | required for backup | `bin/backup.py:78,91`. |

`bin/backup.py:73-85` hard-checks all five `AWS_*` secrets and exits non-zero if
any are missing. Additional infra secret names appear in `samples/secrets/itsup.txt`
(`TRAEFIK_ADMIN`, `CROWDSEC_API_KEY`, `CROWDSEC_CAPI_MACHINE_ID`,
`CROWDSEC_CAPI_PASSWORD`, `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`,
`OPENAI_API_KEY`) for consumption as `${VAR}` in `projects/*.yml` overrides
(e.g. `samples/projects/middlewares.yml`); they have no Python read site.

### Project secrets (`secrets/{project}.{enc.txt|txt}`)

Project secret names are arbitrary and project-defined. They are referenced as
`${VAR}` in that project's `docker-compose.yml` and expanded by Docker Compose at
deploy time (e.g. `samples/projects/example-project/docker-compose.yml:6`
`API_KEY: ${MY_PROJECT_API_KEY}`). itsUP does not define or validate them.

## Known caveats

- **`${VAR}` is expanded by Docker Compose, not by itsUP.** Generated artifacts
  and loaded config keep placeholders literal; the value only materializes when
  `get_env_with_secrets` feeds the env into `docker compose up`. A literal
  `${VAR}` in a running container means the secret was absent from the loaded
  context, not that expansion "failed."
- **Always start compose via `get_env_with_secrets`, never bare `docker compose`.**
  Bare invocation runs with only `os.environ`, so no secret from `secrets/*` is
  present and every `${VAR}` resolves empty.
- **Secrets are per-context and never merged.** A project deploy cannot read
  `secrets/itsup.*`; a value a project needs must be duplicated into that
  project's own secrets file.
- **`get_env_with_secrets` does not validate.** Required-variable enforcement
  lives at the consumer (`bin/backup.py` for `AWS_*`, `lib/auth.py` for
  `API_KEY`, `${VAR:?}` in templates), not in the loader.
- **CLI verbosity ignores `LOG_LEVEL`.** The `itsup` CLI sets its level from
  `-v`/`-vv`; `LOG_LEVEL` only affects non-CLI entrypoints.

## See Also

- docs/project/spec/secrets-management.md
- docs/project/spec/project-config.md
- docs/project/design/network-segmentation.md
