---
description: 'The infrastructure config contract — projects/itsup.yml (routerIP, traefikDomain, versions, crowdsec, backup) loaded as a raw dict and fed to the proxy templates, plus the projects/traefik.yml and projects/middlewares.yml override files deep-merged on top of generated base config.'
---

# itsUP Config — Spec

## What it is

`projects/itsup.yml` is the **infrastructure-wide** configuration for the itsUP
host itself — distinct from the per-project routing contract
`itsup-project.yml` (see `project/spec/project-config`). It holds settings
shared by the proxy/DNS/backup machinery: the Traefik dashboard domain, image
versions, the CrowdSec bouncer config, the router IP, and backup exclusions.

It is loaded as a **raw mapping**, not a model: `load_itsup_config()`
(`lib/data.py:453-470`) returns `yaml.safe_load(...)` (or `{}` if the file is
missing) with secrets left as `${VAR}` placeholders — never expanded at load
time. There is no Pydantic schema and no validation pass over these keys;
consumers read keys directly with `.get(...)` defaults, so an unknown or
mistyped key is silently ignored rather than rejected. The only hard
requirement is `traefikDomain` (see Canonical fields).

Two companion files in `projects/` carry **native Traefik YAML** and are
**deep-merged on top of** itsUP's generated base config (override wins on key
collisions; nested dicts merge recursively — `deep_merge`,
`bin/write_artifacts.py:336-344`):

- **`projects/traefik.yml`** — merged onto the generated `proxy/traefik/traefik.yml`
  static config (`load_traefik_overrides` → merge, `bin/write_artifacts.py:402-411`).
- **`projects/middlewares.yml`** — merged onto the generated
  `proxy/traefik/dynamic/middlewares.yml` dynamic config
  (`load_middleware_overrides` → merge, `bin/write_artifacts.py:467-476`).

Both override files use the full Traefik v3 schema, keep secrets as `${VAR}`
(expanded by Traefik's own `{{ env "VAR" }}` / the deploy env at runtime), and
are optional — absence logs a warning and uses the generated base alone.

## Canonical fields

Top-level keys of `projects/itsup.yml` (verified against the live readers; the
sample is `samples/projects/itsup.yml`):

| Key | Type | Required | Consumed by | Meaning |
|-----|------|----------|-------------|---------|
| `traefikDomain` | str | **yes** | `bin/write_artifacts.py:492-499` | Traefik dashboard host; becomes the dashboard router rule `Host(\`...\`)` (`write_artifacts.py:592`). Missing/empty raises a `ValueError` during artifact generation. |
| `routerIP` | str | no (auto-detected) | `lib/data.py:401` | Router/gateway IP. Used to build Traefik's trusted-IPs list as `{routerIP}/32` (`get_trusted_ips`, `lib/data.py:447-450`). If absent, itsUP auto-detects via `netifaces` and writes the value back into the file (`get_router_ip`/`update_itsup_yml_router_ip`, `lib/data.py:393-444`). |
| `versions` | map | no | `tpl/docker-compose.yml.j2:37,70` | Image tag pins for the proxy stack. |
| `versions.traefik` | str | no | `tpl/docker-compose.yml.j2:37` | Traefik image tag (e.g. `v3.6.17`); rendered as `image: traefik:{{ itsup.versions.traefik }}`. |
| `versions.crowdsec` | str | no | `tpl/docker-compose.yml.j2:70` | CrowdSec image tag; rendered as `image: crowdsecurity/crowdsec:{{ itsup.versions.crowdsec }}`. |
| `crowdsec` | map | no | `bin/write_artifacts.py:430` | CrowdSec bouncer settings. |
| `crowdsec.enabled` | bool | no (default `False`) | `write_artifacts.py:454`; `tpl/docker-compose.yml.j2:50,66` | Gates the CrowdSec service + bouncer middleware. When false, no `crowdsec` container is generated and the bouncer block is omitted. |
| `crowdsec.apikey` | str | no (default `""`) | `write_artifacts.py:455`; `tpl/middlewares.yml.j2:43` | LAPI key injected into the bouncer middleware (`crowdsecLapiKey`). Typically `${CROWDSEC_APIKEY}`. |
| `crowdsec.collections` | str[] | no | `tpl/docker-compose.yml.j2:82` | CrowdSec collections; space-joined into the container's `COLLECTIONS` env. |
| `backup` | map | no | `samples/projects/itsup.yml` | Documentary holder for the S3 endpoint settings below; the live S3 credentials are read from `secrets/itsup.{enc.txt\|txt}`, not from this map. Live-tar exclusions are not configured here — each project declares its own `projects/<name>/backup.yml` (adapter + exclude paths; see `project/design/backup-restore`). |
| `backup.s3.host` | str | no | `samples/projects/itsup.yml` | S3 endpoint host (typically `${AWS_S3_HOST}`). |
| `backup.s3.region` | str | no | `samples/projects/itsup.yml` | S3 region (typically `${AWS_S3_REGION}`). |
| `backup.s3.bucket` | str | no | `samples/projects/itsup.yml` | Target bucket (typically `${AWS_S3_BUCKET}`). |
| `schemaVersion` | str | no | `lib/migrations.py:24,38` | Config schema version, owned by the migration machinery — see `project/spec/schema-migration`. |

<!-- planned:ops-failure-alerting -->

### Alert command

`alert.command` holds the operator's failure-notification transport as a command
template. itsUP composes the alert and hands it to that command; nothing in this
repository knows or names a transport.

| Key | Type | Required | Meaning |
|-----|------|----------|---------|
| `alert` | map | no | Ops failure-alerting settings. |
| `alert.command` | str | no (default: unset) | Command template run for each composed alert. Unset — key, map, or file absent — is a valid configuration: no command runs, the suppressed alert is recorded in the journal, and the composer exits successfully. |

Contract of the template:

- **It is argv, not a shell line.** The template is split into arguments once,
  before any placeholder resolves, and executed without a shell. A `${VAR}`
  placeholder resolves inside the argument that carries it, so a value holding
  whitespace or shell metacharacters stays one argument and can never introduce
  another argument or command.
- **`${VAR}` placeholders resolve from the itsUP infrastructure secrets**
  (`secrets/itsup.{enc.txt|txt}`, loaded per-context — see
  `project/spec/secrets-management`). A token-bearing transport therefore holds
  its credential in the secrets file and only its placeholder in
  `projects/itsup.yml`.
- **A malformed or unresolvable command fails at the boundary, before any child
  process starts.** `alert.command` is valid only when it is a non-empty string
  that splits to a non-empty argument vector and every `${VAR}` it names resolves
  to a non-empty secret. A value that is not a string, splits to nothing, or
  references an absent secret is rejected with a diagnostic naming the offending
  key or placeholder — it is never silently substituted with an empty value.
  This is the one place `${VAR}` does **not** follow itsUP's compose-passthrough
  behaviour, because the resolved value is executed rather than passed to a
  container: an empty substitution there would run a different command than the
  operator configured.
- **The alert body arrives on the command's standard input**; it is never
  interpolated into an argument. The failed unit's identity is additionally
  available to the command in its environment.
- **Secret values never enter an alert body** — names at most.

<!-- /planned:ops-failure-alerting -->

### Override-merge model

`itsup apply` / `bin/write_artifacts.py` first renders minimal **base** configs
from the `tpl/` templates (structure, trusted IPs, dynamic entrypoints/routers,
the CrowdSec base middleware), then `deep_merge`s the user override file on top:

- `traefik.yml` (static) and `middlewares.yml` (dynamic) merge per-key —
  override values replace base scalars/lists; nested maps recurse
  (`deep_merge`, `bin/write_artifacts.py:336-344`).
- Both base and override are parsed with `ruamel.yaml` to preserve comments, and
  the result is written only if changed (`write_file_if_changed`).
- `${VAR}` / `{{ env "VAR" }}` placeholders are left intact in the merged output
  — Traefik resolves them from its runtime environment at deploy.

## Known caveats

- **No validation of itsup.yml keys.** Unlike `itsup-project.yml`
  (`TraefikConfig` model + `itsup validate`), the infra config is a raw dict;
  typos in `routerIP`, `versions`, `crowdsec`, or `backup` fail silently
  (consumers fall back to their `.get(...)` defaults). The single exception is
  `traefikDomain`, whose absence raises during artifact generation.
- **`routerIP` is self-mutating.** When empty, the first run auto-detects and
  rewrites the file in place via regex on the `routerIP:` line
  (`lib/data.py:434-439`); the file is therefore not purely declarative.

## See Also

- docs/project/spec/project-config.md — the per-project itsup-project.yml contract.
- docs/project/spec/schema-migration.md — schemaVersion and the migration fixers.
- docs/project/spec/secrets-management.md — how ${VAR} placeholders are resolved.
