---
description: 'How itsUP turns declarative projects/ config into deployable artifacts — Traefik label injection (HTTP) vs dynamic-file routers (TCP/UDP/host), template+override merge, DNS injection, and static-IP pinning, all via change-detecting writes.'
---

# Artifact Generation — Design

## Purpose

itsUP is declarative: operators edit `projects/`, and `bin/write_artifacts.py`
generates the concrete Docker Compose + Traefik files that actually run. Nobody
hand-writes Traefik labels, routers, or entrypoints — they are derived from
`itsup-project.yml` ingress rows plus Jinja2 templates merged with user
overrides. This snippet is the contract for that translation. Network assignment
(proxynet/egress) is covered separately in `project/design/network-segmentation`.

## Inputs/Outputs

**Inputs**

- `projects/{project}/itsup-project.yml` (`TraefikConfig`) + `docker-compose.yml`.
- `projects/itsup.yml` — infra config: image `versions`, `traefikDomain`,
  `routerIP`, `crowdsec`.
- `projects/traefik.yml`, `projects/middlewares.yml` — user overrides
  (optional).
- `tpl/*.j2` — `traefik.yml.j2`, `routers-http.yml.j2`, `routers-tcp.yml.j2`,
  `routers-udp.yml.j2`, `middlewares.yml.j2`, `docker-compose.yml.j2`.
- Infra secrets (`secrets/itsup.{enc.txt|txt}`) — e.g. `TRAEFIK_ADMIN`.

**Outputs**

- `upstream/{project}/docker-compose.yml` — services + injected
  labels/networks/DNS.
- `proxy/traefik/traefik.yml` — static config + entrypoints.
- `proxy/traefik/dynamic/{routers-http,routers-tcp,routers-udp,middlewares}.yml`.
- `proxy/docker-compose.yml`.

**Entry points** — `write_proxy_artifacts()` (proxy side) and `write_upstreams()`
(per-project). `bin/write_artifacts.py` regenerates without deploying;
`itsup apply` regenerates then deploys.

## Invariants

1. **HTTP ingress → Docker labels; TCP/UDP → dynamic-file routers.**
   `inject_traefik_labels()` (`bin/write_artifacts.py:70`) emits labels **only**
   for `router: http` rows. TCP/UDP label generation is intentionally disabled
   (`:136-153`) because they need dedicated entrypoints declared in `traefik.yml`;
   they are instead rendered as dynamic-file routers + entrypoints
   (`write_dynamic_routers`, `write_traefik_config`). Router/service name is
   `{project}-{service}-{port}` (`:95`).
2. **HTTP label set** (`:102-131`): `traefik.enable=true`,
   `entrypoints=web-secure`, host rule from `tls.main+sans` else `domain`,
   `tls=true`, `tls.certresolver=letsencrypt`, SANs via `tls.domains[0]`, and
   `loadbalancer.server.port`. A companion `{router_name}-redirect` router is
   also emitted on the plain `web` entrypoint, same host rule, with
   `middlewares=redirect@file` sending it to HTTPS — skipped only for the
   `ACME_CHALLENGE_PATH_PREFIX` passthrough carve-out, which must reach its
   backend unredirected. The `web` entrypoint enables Traefik's ACME bypass so
   a more-specific challenge router can forward that carve-out while Traefik's
   internal router continues handling its other HTTP-01 challenges.
3. **Entrypoints.** Static `web:8080` / `web-secure:8443` always exist; `web`
   enables `allowACMEByPass` so an explicitly declared challenge route can
   outrank Traefik's internal ACME router. Dynamic
   entrypoints `{router}-{hostport|port}` are generated per TCP/UDP/hostport
   ingress (`traefik.yml.j2`). Passthrough **without** hostport reuses
   `web-secure` (no new entrypoint, `:329-333`).
4. **External-host projects** (`TraefikConfig.host` set) route to that host:port
   via dynamic routers (`:493-499`); pinned-IP container ingress uses
   `ipv4_address or service` as the backend (`:511`).
5. **Override merge.** `deep_merge` (`:301`) merges `projects/traefik.yml` /
   `projects/middlewares.yml` **on top of** the generated base, comment-preserving
   (ruamel). Missing override file ⇒ warning, base only.
<!-- planned-change:dns-fallback-off-proxynet -->
6. **DNS injection.** Every upstream service gets
   `dns: [172.20.0.253, 127.0.0.11]` (honeypot + Docker DNS) unless its ingress
   row sets explicit `dns`, which is written verbatim (`:213-221`). The honeypot
   logs queries for security monitoring (see `docs/networking.md`).
<!-- change:dns-fallback-off-proxynet -->
6. **DNS injection.** Every upstream service gets `dns: [172.20.0.1]` — the
   honeypot reached at the proxynet gateway address, which the host owns and
   every container network can reach — unless its ingress row sets explicit
   `dns`, which is written verbatim (`:213-221`). The list carries exactly one
   entry: Docker's embedded resolver already answers sibling names from the
   service's own network namespace and must never appear as its own upstream,
   and a second public entry would let external lookups bypass the honeypot.
   The honeypot logs queries for security monitoring (see `docs/networking.md`).
<!-- /planned-change:dns-fallback-off-proxynet -->
7. **Static IP pinning.** An ingress `ipv4_address` rewrites that service's
   `networks:` to mapping form pinning the IP on proxynet; the service must be on
   proxynet or it is skipped with a warning (`:244-265`).
8. **Change-detecting writes.** `write_file_if_changed` (`:38`) rewrites a file
   only when content differs. Unchanged artifacts keep their bytes, so deploys
   become no-ops via Docker's config-hash (see
   `project/design/deployment-orchestration`).
9. **External-host router identity is per-route unique.** An external-host
   dynamic router's name is `{project}-{host}-{port}` plus the route's index
   within that host's ingress list, so two ingress rows sharing one `host:port`
   (e.g. an open `/redirect` and a gated `/file`) generate two distinct routers
   (and matching services) instead of colliding on one router key. The index
   suffix is unique by construction — no lossy path transform, so no separate
   uniqueness validation is needed.
10. **Per-route source-IP gate.** An ingress row carrying `allow_source_ips`
    makes `write_dynamic_routers` emit a Traefik `ipAllowList` middleware
    (`sourceRange` = the declared list) and attach it to that route's router
    alone; routes without the field emit no per-route middleware. This is the
    per-route counterpart to the global entrypoint chain
    (`project/spec/feature/deployment/http-security-middlewares`). Contract:
    `project/spec/feature/deployment/route-scoped-ip-allowlist`.

<!-- planned:cross-platform-project-network-rules -->
11. **Host firewall rules are derived artifacts.** Project networking intent
    produces platform-native rules for OpenSnitch on Linux and Little Snitch on
    macOS; agents do not hand-author per-project rule files. Applying those
    artifacts is optional and does nothing when the applicable filter is absent.
    Rule generation remains independent from publication or upload transport.
<!-- /planned:cross-platform-project-network-rules -->

## Primary flows

### Proxy artifacts (`write_proxy_artifacts`, `:617`)

`write_traefik_config` (collect TCP/UDP entrypoints + merge overrides) →
`write_middleware_config` (CrowdSec + `TRAEFIK_ADMIN` + overrides) →
`write_dynamic_routers` (http/tcp/udp router files for hostport/passthrough/
external-host ingress) → `write_proxy_compose` (from `docker-compose.yml.j2`).

### Upstream compose (`write_upstream`, `:158`, per project)

Load project → inject HTTP labels → assign networks (proxynet for ingress,
egress targets, project default) → inject DNS → pin static IPs → write
`upstream/{project}/docker-compose.yml` if changed.

## Failure modes

- **Ingress references unknown service** — label injection logs a warning and
  skips that row (`:79-80`); `validate_all` also reports it and blocks deploy.
- **Missing `TRAEFIK_ADMIN` secret** — `write_middleware_config` /
  `write_dynamic_routers` raise `ValueError` (`:401-406`, `:470-475`).
- **Missing `traefikDomain`** in `itsup.yml` — `write_dynamic_routers` raises
  (`:458-464`).
- **Missing override file** — warning; generated base is used alone.
- **`__main__` runs `validate_all()` first** and exits non-zero on any project
  error before generating (`:629-635`).

## See Also

- docs/project/spec/project-config.md
- docs/project/design/network-segmentation.md
- docs/project/design/network-segmentation.md
