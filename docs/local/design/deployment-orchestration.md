---
description: 'How itsUP deploys generated artifacts — zero-downtime rollout via the docker-rollout plugin, volume-inferred statelessness, config-hash change detection, and the apply/run/down stack orchestration with egress-topological ordering.'
---

# Deployment & Orchestration — Design

## Purpose

itsUP deploys the artifacts produced by `local/projects/itsup/design/artifact-generation`
with two goals: **zero downtime** for replaceable services and **idempotence**
(skip work when nothing changed). It also orchestrates the multi-stack lifecycle
(DNS, proxy, API, monitor, upstream projects) in a dependency-correct order.

## Inputs/Outputs

**Inputs** — generated `upstream/{project}/`, `proxy/`, `dns/` compose files;
per-context secrets via `get_env_with_secrets` (`lib/data.py:88`).
**Outputs** — running/updated/stopped containers.
**Surfaces** — `itsup apply [project]`, `itsup run`, `itsup down [--clean]`,
`itsup svc <project> <cmd>`. Core engine: `lib/deploy.py:smart_deploy`.

## Invariants

1. **Rollout is delegated to the external `docker rollout` plugin.**
   `rollout_service` runs `docker rollout <service>` (`lib/deploy.py:167`); the
   scale-up→health-check→kill-old→scale-down sequence is the plugin's, not
   itsUP's.
2. **Statelessness is inferred from volume absence — not a config flag.**
   `deploy_upstream_project` treats a service as stateless iff it declares no
   `volumes` (or is named `traefik`) (`lib/deploy.py:360-364`). The
   `Service.stateless` model field (`lib/models.py:151`) is **never read** (dead;
   see `local/projects/itsup/spec/project-config`). Infra stacks hardcode their lists: proxy
   `["traefik"]` (`:299`), DNS `[]` (`:281`).
3. **Rollout fires only when needed.** A stateless service is rolled out only if
   it was running **before** this deploy (`:252`) **and** either its config hash
   changed (`:257`) **or** the deploy forces its rollout. First-time deploy =
   plain `up -d`, no rollout. A rollout failure is logged and **does not fail the
   deploy** (`:264-266`). The proxy deploy forces a `traefik` rollout when its
   regenerated bind-mounted static config (`proxy/traefik/traefik.yml`) changed —
   content invariant 4's Docker-native hash cannot see, since it is bind-mounted
   rather than part of the compose definition
   (`local/projects/itsup/spec/feature/deployment/mounted-config-propagation`).

4. **Change detection is Docker-native.** `service_needs_update` compares
   `docker compose config --hash <service>` against the running container's
   `com.docker.compose.config-hash` label (`:73-134`); no running container, or
   any error, ⇒ assume update.
5. **`enabled: false` stops, not deploys.** A disabled project is brought down
   (`docker compose down`, `:333-352`); host-only projects skip entirely.
6. **`apply` is gated and ordered.** It runs `check_schema_version()` then the
   fail-closed `validate_all()` — any project error blocks **all** deploys
   (`commands/apply.py:40-51`). All-projects order is `["dns","proxy"]` +
   `list_projects_topo()` (egress targets first; `lib/data.py:220`), run
   **sequentially**, no early termination — failures collected, `exit(1)` at end.
7. **Secrets are injected per subprocess.** Every compose/rollout call gets
   `env=get_env_with_secrets(project)`; `${VAR}` placeholders survive into
   generated files and Compose expands them at runtime
   (see `local/projects/itsup/spec/secrets-management`).

## Primary flows

### `itsup apply` — deploy/update

Validate gate → for each target in dependency order, `deploy_*` →
`smart_deploy` (pull → `up -d` → conditional rollout of stateless services).

### `itsup run` — orchestrated boot

`check_schema_version` → regenerate proxy artifacts → DNS `up -d` (creates
`proxynet`) → proxy `up -d` → start the API daemon unit → start the monitor
daemon unit in report-only mode, both through the host supervisor
(`commands/run.py`). **Divergence:** `run` uses plain `docker compose up -d`,
bypassing `smart_deploy`/rollout — boot is not zero-downtime (it is the
cold-start path).

### `itsup down` — orchestrated shutdown

monitor unit (stop) → API unit (stop) → all projects in parallel (`down`) →
proxy → DNS (`commands/down.py`). `--clean` additionally `rm -f`s itsUP-managed
stopped containers.

## Failure modes

<!-- planned-change:dns-fallback-off-proxynet -->
- **Outdated config schema** — `check_schema_version` errors and exits before
  any command runs; operator must `itsup migrate` (see
  `local/projects/itsup/spec/schema-migration`).
- **Image pull failure** — tolerated (`check=False`, `:224`) so local-only
  images deploy.
- **Running-state probe failure** — fatal for that target. `service_is_running`
  reports only what it determined: `docker ps` exits zero with empty output when
  nothing matches, so any failure of the probe itself — an unreachable daemon, a
  missing binary, a permission error — propagates rather than being reported as
  "not running".
- **Rollout failure** — logged, non-fatal; the `up -d` containers still run.
- **Any project validation error** — `validate_all` blocks the entire `apply`.
- **Egress dependency cycle** — `list_projects_topo` falls back to alphabetical
  with a warning; an external `{target}_default` may not exist yet, failing that
  project's `up` (see `local/projects/itsup/design/network-segmentation`).
<!-- change:dns-fallback-off-proxynet -->
- **Outdated config schema** — `check_schema_version` errors and exits before
  any command runs; operator must `itsup migrate` (see
  `local/projects/itsup/spec/schema-migration`).
- **Image pull failure** — tolerated (`check=False`, `:224`) so local-only
  images deploy.
- **Running-state probe failure** — fatal for that target. `service_is_running`
  reports only what it determined: `docker ps` exits zero with empty output when
  nothing matches, so any failure of the probe itself — an unreachable daemon, a
  missing binary, a permission error — propagates rather than being reported as
  "not running".
- **Rollout failure** — logged, non-fatal; the `up -d` containers still run.
- **Any project validation error** — `validate_all` blocks the entire `apply`.
- **Egress dependency cycle** — `list_projects_topo` falls back to alphabetical
  with a warning; an external `{target}_default` may not exist yet, failing that
  project's `up` (see `local/projects/itsup/design/network-segmentation`).
- **DNS stack on a VM-backed Docker runtime** — the honeypot's resolver is
  published on the proxynet gateway address, which only a host that owns its
  bridges can bind. Under a VM-backed runtime the bridges live inside the virtual
  machine, so the daemon rejects the binding and the DNS stack does not start.
  Such a host is not a supported container host.
<!-- /planned-change:dns-fallback-off-proxynet -->

## See Also

- docs/local/design/artifact-generation.md
- docs/local/spec/secrets-management.md
