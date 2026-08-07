---
description: 'The itsUP management REST API — apikey-guarded webhook endpoints that trigger deploys (including a production self-update that hard-resets to origin/main) and list projects.'
---

# API Surface — Spec

## What it is

A small FastAPI app (`api/main.py`, title `itsUP API` v2.0) that lets external
systems trigger deploys via webhook and query projects. It is **not**
containerized — it runs as a host process on `:8888`, supervised by the host as
a daemon unit.

Its Traefik routes are scoped to the two endpoints that need the internet, each
its own `Host(...) && PathPrefix(...)` router: the unauthenticated `/redirect`
bouncer and the origin-gated `/file` endpoint. Each is a **path prefix, not an
exact route** — it admits any method and any path beginning with its prefix, and
nothing else is served under either prefix, so a request under a prefix that no
handler serves is answered `405` or `404` by FastAPI. `/redirect` is
unauthenticated; `/file` carries a route-scoped source-IP allowlist at the proxy
(`project/spec/feature/deployment/route-scoped-ip-allowlist`) so only the
allowlisted origin reaches it.

The apikey-guarded endpoints share no prefix with it and so carry no public route
at all — an internet request for one of them fails to match a router and is
refused by the proxy before the API sees it, rather than reaching the API and
being rejected by the API key. Those endpoints are served
over plain HTTP on `:8888` to callers already inside the boundary: the container
host itself over loopback, and LAN or VPN clients at the host's LAN address. The
hostname and its Let's Encrypt certificate are unaffected — ACME HTTP-01
resolves at the `web` entrypoint, ahead of router matching.
Every mutating/data
endpoint is guarded by an API key (`verify_apikey`, `lib/auth.py`, via FastAPI
`Depends`). Deploy work runs in a FastAPI `BackgroundTask`; the endpoint returns
immediately.

## Canonical fields

### Endpoints (`api/main.py`)

| Method/Path | Auth | Reachable from | Behaviour |
|-------------|------|----------------|-----------|
| `GET /update-upstream/{project}` | apikey | host loopback, LAN/VPN | Background-deploys one project via `.venv/bin/itsup apply {project}` (`:27-36,84-93`). Unknown project ⇒ logged and ignored. |
| `GET /update-upstream/{project}/{service}` | apikey | host loopback, LAN/VPN | Same, scoped to one service. |
| `POST /reconcile` | apikey | host loopback, LAN/VPN | Background full-stack reconcile: pulls the `projects`/`secrets` config repos then runs `itsup apply`; single-flight with trailing-run coalescing (`lib/reconcile.py`). |
| `GET /projects` | apikey | host loopback, LAN/VPN | Returns `list_projects()` (`@cache`d, `:96-100`). |
| `GET /redirect?url=` | none | internet | 307-redirects, but **only** `message://` / `imessage://` schemes; rejects other schemes or whitespace (`:103-116`). Consumer: OtoMo (`lib/deep_links.py`) wraps iMessage deep links in this endpoint so Telegram renders them as clickable https links. |
<!-- planned:lsrules-upload-endpoint -->
| `PUT /upload/{name}` | apikey | host loopback, LAN/VPN | Stores the request body as `{name}` in the itsUP-owned upload directory, replacing any existing file, and reports the stored location. `{name}` must be a single path segment with an allowlisted extension; the body size is bounded. Feeds `GET /file`. Contract: `project/spec/feature/api/gated-file-serving`. |
<!-- /planned:lsrules-upload-endpoint -->

### Gated file endpoint (`GET /file`)

`GET /file?path=<host-path>` serves the bytes of a local host file selected by
path, over the internet, to an origin-gated caller. It carries no app-side
authentication: the origin gate is a route-scoped source-IP allowlist at the
proxy (`project/spec/feature/deployment/route-scoped-ip-allowlist`), and the
app-side security boundary is a positive file-extension allowlist (initially
`.lsrules`) that refuses config/secret formats by construction. A
non-allowlisted extension, or a path that is not an existing regular file, is
refused with a client-error status; an allowlisted-extension file is returned
with its bytes and the content type mapped for that extension. `path` is a
required query parameter, so omitting it is rejected by FastAPI's own request
validation rather than by the endpoint. Behaviour contract:
`project/spec/feature/api/gated-file-serving`.

The GitOps chain reaches the apikey-guarded endpoints over loopback: the shared
reconcile workflow's `curl` runs on the container host itself, inside the SSH
step that follows its VPN connection. Ad-hoc triggering from outside the network
is not available; an operator reaches these endpoints over LAN or VPN.

<!-- planned:lsrules-upload-endpoint -->

### Publishing the upload route (operator decision)

`PUT /upload/{name}` follows the posture above: with no router for its path
prefix it is reachable only over loopback, LAN, or VPN. A producer that must
upload from outside the network needs a route, which is added in the separate
`itsUP-projects` repository:

```yaml
  - domain: itsup.srv.instrukt.ai
    path_prefix: /upload
    port: 8888
    router: http
```

The row carries no `allow_source_ips`. An origin allowlist here would refuse the
off-network producer the route exists for, and the API key — not the origin — is
the write boundary.

Publishing it also makes the route count above wrong: the internet-facing routes
become three rather than two, and the API-key endpoints no longer all lack a
public route. Whoever publishes the row updates those statements in the same
change.

Publishing that row makes an API-key-guarded **write** endpoint reachable from
the internet, so the key alone stands between the internet and a file written to
the host that holds the SOPS age key. That is a wider exposure than the routed
read endpoints, whose worst case is disclosure of an allowlisted file. The
trade is the operator's to accept: leaving the row unpublished keeps the
endpoint on the network-boundary posture and restricts producers to LAN or VPN.

<!-- /planned:lsrules-upload-endpoint -->


### Self-update (`project == "itsUP"`)

`GET /update-upstream/itsUP` triggers `_handle_itsup_update` (`:39-66`): in
`PYTHON_ENV=production` it **`git fetch origin main` + `git reset --hard
origin/main`** (destructive — discards local changes to the itsUP checkout),
then redeploys DNS + proxy stacks (`smart_deploy`) and `.venv/bin/itsup apply` (all
projects), then restarts the API. This is the unattended self-update path.

After the dependency sync — on Linux only, where the container host runs — the
self-update **detects** whether the delivery left the host's installed systemd
units drifted from the delivered `samples/systemd/*` templates
(`bin/install-bringup.sh --check-drift`: a read-only render-and-compare of each
template against `/etc/systemd/system`, dispatched before the installer's host gate
and any mutating step, so it holds no privilege and mutates nothing). On drift it
**always logs** the drifted units and the one-command remedy `make install-runtime`
to the journal, and — **when `alert.command` is configured** — additionally raises
the operator alert with the same content through `bin/alert.py --drift-units` (a
third alert kind alongside unit-failure and the apply deadman), suppressing exactly
as those do when the transport is unset. Installing the units stays the operator's
privileged, gated step; the self-update guarantees the staleness is recorded rather
than passing unnoticed. The detection and alert are non-fatal — a failure logs but
never aborts the self-update — and are skipped with a logged notice on macOS.

### Server

Uvicorn on `0.0.0.0:8888`; `proxy_headers`/forwarded IPs trusted only in
production (`:119-130`). OpenAPI schema is extractable via
`api/extract-openapi.py`.

## Known caveats

- **Webhook deploys are `GET`s with side effects** — chosen for webhook-provider
  compatibility; the API key is the only guard, so treat the key as a deploy
  credential.
- **Self-update is a hard reset** — `git reset --hard origin/main` in production
  means any uncommitted change on the host checkout is lost on a self-update
  webhook.

## See Also

- docs/project/design/deployment-orchestration.md
