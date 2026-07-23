---
description: 'The per-project declarative configuration contract — itsup-project.yml (TraefikConfig/Ingress/Egress/TLS + enums) and the docker-compose.yml it accompanies, including validation rules and the two project types (container vs external host).'
---

# Project Config — Spec

## What it is

A project lives in `projects/{project}/` and is described by two files:

- **`docker-compose.yml`** — a standard Compose file (services, images, volumes,
  env with `${VAR}` placeholders). itsUP loads it as a **raw mapping**
  (`yaml.safe_load`, `lib/data.py:168`), not through a model; the validation
  gate enforces Compose-schema validity (see Validation rules), and itsUP only
  injects networks/labels/DNS at generation time. The
  author writes only the service definitions: ingress, Traefik labels, networks,
  and DNS are declared in `itsup-project.yml` and injected downstream, never
  hand-written here. Two authoring constraints the raw-mapping load does **not**
  enforce but the platform depends on:
  - **Persist with bind mounts, never named volumes.** The nightly backup tars
    only bind-mounted state under `upstream/`
    (`project/procedure/backup-and-restore`); a named volume lives outside that
    tree and is silently lost on restore.
  - **Give each service a healthcheck.** The zero-downtime rollout waits on it
    (`scale-up → health-check → kill-old`,
    `project/design/deployment-orchestration`) and `depends_on: service_healthy`
    gating relies on it.
- **`itsup-project.yml`** (legacy name `ingress.yml`, deprecated — see
  `project/design/network-segmentation`) — the itsUP routing + segmentation
  contract, parsed into the `TraefikConfig` model (`lib/data.py:199`).

A project is one of two **types**, decided by file presence
(`lib/data.py:load_project`):

- **Container project** — has `docker-compose.yml`; services are generated into
  `upstream/{project}/` and deployed.
- **External-host passthrough** — no `docker-compose.yml`; `itsup-project.yml`
  sets `host:` and Traefik routes to that host:port. No containers deployed.

`itsup validate [project]` checks every project; `validate_all()`
(`lib/data.py:365`) is the fail-closed gate run before any artifact write/deploy.

## Canonical fields

### `TraefikConfig` (root of itsup-project.yml) — `lib/models.py:180-191`

| Field | Type | Default | Meaning |
|-------|------|---------|---------|
| `enabled` | bool | `true` | When `false`, deploy **stops** the project instead of running it (`lib/deploy.py:333`). |
| `host` | str \| null | `null` | External host IP/hostname for container-less passthrough projects. |
| `ingress` | `Ingress[]` | `[]` | Services exposed via Traefik. |
| `egress` | `str[]` | `[]` | Cross-project access, each `"{project}:{service}"`. See `project/design/network-segmentation`. |

### `Ingress` row — `lib/models.py:72-108`

| Field | Type | Default | Meaning |
|-------|------|---------|---------|
| `service` | str \| null | `null` | Compose service name (container projects). |
| `domain` | str \| null | `null` | Public domain; omitted ⇒ not publicly routed. Drives TLS termination. |
| `hostport` | int \| null | `null` | Host port to expose; triggers a dedicated Traefik entrypoint. |
| `passthrough` | bool | `false` | Forward TLS as-is (no termination). |
| `path_prefix` | str \| null | `null` | Route under a path prefix. |
| `path_remove` | bool | `false` | **Declared but not wired into label generation** (see caveats). |
| `port` | int | `8080` | Backend service port. |
| `protocol` | `Protocol` | `tcp` | `tcp` \| `udp`. |
| `proxyprotocol` | `ProxyProtocol` \| null | `v2` | PROXY-protocol version; explicit `null` disables. |
| `router` | `Router` | `http` | `http` \| `tcp` \| `udp`. Only `http` produces docker labels; `tcp`/`udp` produce dynamic-file routers (see `project/design/artifact-generation`). |
| `tls` | `TLS` \| null | `null` | `{main, sans[]}`; used instead of `domain`. |
| `ipv4_address` | str \| null | `null` | Static IP pinned on proxynet; must lie in `172.20.0.0/16`. |
| `dns` | str[] \| null | `null` | Explicit DNS servers; written verbatim, replacing the honeypot default. |

`TLS` (`lib/models.py:63-69`): `main: str`, `sans: str[]`.
Enums: `Protocol` = `tcp|udp`; `ProxyProtocol` = `v1|v2`; `Router` = `http|tcp|udp`.

<!-- planned:gated-file-endpoint -->
### Route-scoped source-IP allowlist (`Ingress.allow_source_ips`)

| Field | Type | Default | Meaning |
|-------|------|---------|---------|
| `allow_source_ips` | str[] \| null | `null` | Source IPs/CIDRs permitted to reach this route's Traefik router — the proxy-side origin gate. When set, generation emits a per-route `ipAllowList` middleware (`sourceRange`) attached to this route only (`project/design/artifact-generation`, `project/spec/feature/deployment/route-scoped-ip-allowlist`). Each entry must parse as an IP address or CIDR network. |
<!-- /planned:gated-file-endpoint -->

### Validation rules

- **Ingress→service existence** — every `ingress.service` must exist in the
  project's compose services (`lib/data.py:350-354`).
- **External host** — a container-less project must set `host`
  (`lib/data.py:343-345`).
- **Static IP** (`_validate_ingress_ips`, `lib/data.py:265`) — `ipv4_address`
  must be valid IPv4, inside `172.20.0.0/16`, not a reserved IP
  (`172.20.0.1` gateway / `172.20.0.253` honeypot), and consistent per service;
  cross-project IP collisions are caught in `validate_all` (`lib/data.py:376-381`).
- **Egress targets** (`_validate_egress_targets`, `lib/data.py:290`) — `"a:b"`
  format; target project must exist; target service must exist in that project.
- **Model validators** (`lib/models.py`) — `passthrough` on port 80 is allowed
  only for `/.well-known/acme-challenge/`; `ipv4_address` must parse as IPv4.
<!-- planned:gated-file-endpoint -->
- **Source-IP allowlist** — when an ingress row sets `allow_source_ips`, each
  entry must parse as an IP address or CIDR network (`ipaddress.ip_network`,
  `lib/models.py`); a malformed entry fails validation.
- **External-host router identity uniqueness** — within a project, the
  generated external-host router identities (`{project}-{host}-{port}` plus the
  sanitized `path_prefix` segment) must be unique; two ingress rows whose path
  prefixes collapse to the same identity fail validation, naming the collision.
<!-- /planned:gated-file-endpoint -->
- **Compose schema** — a container project's `docker-compose.yml` (decided by
  file presence, the project-type discriminator) must pass Docker Compose's own
  schema/semantic validation (`docker compose config --no-interpolate`,
  non-mutating, no containers started); a well-formed-YAML file that is not a
  valid Compose document is rejected with the Compose error surfaced. The check
  is interpolation-independent: it never loads project secrets and its verdict
  is identical on machines without decryption keys — `${VAR}` values, including
  required-variable syntax, do not affect schema validity. When the `docker`
  CLI is unavailable on the machine, the check is skipped with a logged
  warning — validation runs anywhere, and the gate holds wherever Docker is
  present, including the deployment host.

## Allowed values

- `Protocol`: `tcp`, `udp`.
- `ProxyProtocol`: `v1` (=1), `v2` (=2), or `null` (disabled).
- `Router`: `http`, `tcp`, `udp`.

## Known caveats

- **`Ingress.path_remove` is inert.** Declared in the `Ingress` model but not
  wired into label output; path-prefix stripping middleware is not generated.
- **`Service`/`Project` models are legacy V1.** `lib/models.py:128-174` defines
  them, but the V2 path reads `docker-compose.yml` as a raw dict and never
  instantiates them. `Service.stateless` is therefore dead — the deploy path
  infers statelessness from volume absence (see
  `project/design/deployment-orchestration`).
- **`ingress.yml` filename** is deprecated (grace to v3.0); both names load,
  `itsup-project.yml` wins.

## See Also

- docs/project/design/network-segmentation.md
- docs/project/design/artifact-generation.md
- docs/project/procedure/backup-and-restore.md
- docs/project/design/deployment-orchestration.md
