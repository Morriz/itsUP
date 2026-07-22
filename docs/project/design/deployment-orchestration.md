---
description: 'How itsUP deploys generated artifacts — zero-downtime rollout via the docker-rollout plugin, volume-inferred statelessness, config-hash change detection, and the apply/run/down stack orchestration with egress-topological ordering.'
---

# Deployment & Orchestration — Design

## Purpose

itsUP deploys the artifacts produced by `project/design/artifact-generation`
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
   see `project/spec/project-config`). Infra stacks hardcode their lists: proxy
   `["traefik"]` (`:299`), DNS `[]` (`:281`).
3. **Rollout fires only when needed.** A stateless service is rolled out only if
   it was running **before** this deploy (`:252`) **and** its config hash changed
   (`:257`). First-time deploy = plain `up -d`, no rollout. A rollout failure is
   logged and **does not fail the deploy** (`:264-266`).
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
   (see `project/spec/secrets-management`).

## Primary flows

### `itsup apply` — deploy/update

Validate gate → for each target in dependency order, `deploy_*` →
`smart_deploy` (pull → `up -d` → conditional rollout of stateless services).

### `itsup run` — orchestrated boot

<!-- planned-change:native-daemon-supervision -->
`check_schema_version` → regenerate proxy artifacts → DNS `up -d` (creates
`proxynet`) → proxy `up -d` → `bin/start-api.sh` → `bin/start-monitor.sh
--report-only` (`commands/run.py`). **Divergence:** `run` uses plain
`docker compose up -d`, bypassing `smart_deploy`/rollout — boot is not
zero-downtime (it is the cold-start path).

### `itsup down` — orchestrated shutdown

monitor (`pkill`) → API (`pkill`) → all projects in parallel (`down`) → proxy →
DNS (`commands/down.py`). `--clean` additionally `rm -f`s itsUP-managed stopped
containers.
<!-- change:native-daemon-supervision -->
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
<!-- /planned-change:native-daemon-supervision -->

## Failure modes

- **Outdated config schema** — `check_schema_version` errors and exits before
  any command runs; operator must `itsup migrate` (see
  `project/spec/schema-migration`).
- **Image pull failure** — tolerated (`check=False`, `:224`) so local-only
  images deploy.
- **Rollout failure** — logged, non-fatal; the `up -d` containers still run.
- **Any project validation error** — `validate_all` blocks the entire `apply`.
- **Egress dependency cycle** — `list_projects_topo` falls back to alphabetical
  with a warning; an external `{target}_default` may not exist yet, failing that
  project's `up` (see `project/design/network-segmentation`).

## See Also

- docs/project/design/artifact-generation.md
- docs/project/spec/secrets-management.md
