---
description: Acceptance scenario for mounted static Traefik config propagation — a
  deploy that regenerates a changed bind-mounted proxy/traefik/traefik.yml rolls out
  Traefik so the running proxy serves the new static config without a manual restart.
---
# Mounted Config Propagation — Spec

## What it is

itsUP's proxy static configuration (`proxy/traefik/traefik.yml`) is delivered to
Traefik as a read-only **bind mount** (`tpl/docker-compose.yml.j2`), not baked
into the image or the compose definition. Traefik loads that static file once at
process start and its file provider watches only the dynamic directory
(`/etc/traefik/dynamic`), never the static file — so entrypoint-level config
(the CrowdSec bouncer attachment, the default security middlewares, the
entrypoint definitions themselves) takes effect only when the process restarts.

A deploy regenerates the static config on disk but the compose definition is
unchanged, so Docker-native change detection
(`project/design/deployment-orchestration`, invariant 4) is blind to the new
file content and `docker compose up -d` no-ops. This contract closes that gap:
when the regenerated static config content actually changed, the proxy deploy
rolls out Traefik through the existing zero-downtime path so a fresh container
loads the new static config — with no manual restart. When the regenerated
content is byte-identical, no rollout fires, preserving deploy idempotence.

The business value is that a delivered change to enforcement, security
middlewares, or entrypoints goes live on the next deploy instead of sitting
inert on disk until an operator notices and restarts Traefik by hand.

### Use cases

The scenario below is bound by the path-mirrored functional test
`tests/deployment/test_mounted_config_propagation.py`, which drives the real
`deploy_proxy_stack` (and through it the real proxy artifact writer) against an
isolated itsUP tree, faking only the Docker subprocess line, and asserts whether
a `traefik` rollout is invoked.

#### UC-MCP1: A changed mounted static config rolls out Traefik on deploy

```gherkin
Given Traefik is running under the proxy stack
And a proxy deploy regenerates proxy/traefik/traefik.yml with changed content
When the proxy stack is deployed
Then the deploy rolls out the traefik service so a fresh container loads the new static config
And when the regenerated static config content is unchanged the deploy does not roll out traefik on that account
And when Traefik was not running before the deploy the changed static config is served by the first-time up -d fresh container without a rollout
```

## Canonical fields

- **Change signal.** The proxy artifact writer reports whether the regenerated
  static `proxy/traefik/traefik.yml` content changed. This is the sole proxy
  artifact whose change is invisible to both Docker-native change detection (its
  content is bind-mounted, not part of the compose hash) and Traefik's file
  provider (which watches only the dynamic directory) — the dynamic router and
  middleware files hot-reload, and the proxy compose file changes the compose
  hash and is caught by normal change detection.
- **Propagation trigger.** When the static config content changed and Traefik
  was already running before the deploy, the proxy deploy rolls out `traefik`
  through the existing `rollout_service` zero-downtime path regardless of the
  compose config hash. A first-time deploy (Traefik not running before) needs no
  rollout — `docker compose up -d` starts a fresh container that reads the new
  static config.
- **Idempotence.** An unchanged static config produces no rollout on the
  static-config account, preserving the deploy's skip-when-nothing-changed
  behavior (`project/design/deployment-orchestration`).

## See Also

- docs/project/design/deployment-orchestration.md
- docs/project/design/artifact-generation.md
