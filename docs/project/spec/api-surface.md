---
description: 'The itsUP management REST API — apikey-guarded webhook endpoints that trigger deploys (including a production self-update that hard-resets to origin/main) and list projects.'
---

# API Surface — Spec

## What it is

A small FastAPI app (`api/main.py`, title `itsUP API` v2.0) that lets external
systems trigger deploys via webhook and query projects. It is **not**
containerized — it runs as a host process on `:8888` (`bin/start-api.sh`).

Its Traefik route is scoped to the one endpoint that needs the internet: the
public router matches `Host(...) && PathPrefix('/redirect')`. This is a **path
prefix, not an exact route** — it admits any method and any path beginning with
`/redirect`. Nothing else is served under that prefix, so the only endpoint it
reaches is `GET /redirect`; a request such as `POST /redirect` or
`/redirect-anything` is routed to the API and answered `405` or `404` by FastAPI.
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
| `GET /update-upstream/{project}` | apikey | host loopback, LAN/VPN | Background-deploys one project via `bin/itsup apply {project}` (`:27-36,84-93`). Unknown project ⇒ logged and ignored. |
| `GET /update-upstream/{project}/{service}` | apikey | host loopback, LAN/VPN | Same, scoped to one service. |
| `POST /reconcile` | apikey | host loopback, LAN/VPN | Background full-stack reconcile: pulls the `projects`/`secrets` config repos then runs `itsup apply`; single-flight with trailing-run coalescing (`lib/reconcile.py`). |
| `GET /projects` | apikey | host loopback, LAN/VPN | Returns `list_projects()` (`@cache`d, `:96-100`). |
| `GET /redirect?url=` | none | internet | 307-redirects, but **only** `message://` / `imessage://` schemes; rejects other schemes or whitespace (`:103-116`). Consumer: OtoMo (`lib/deep_links.py`) wraps iMessage deep links in this endpoint so Telegram renders them as clickable https links. |

The GitOps chain reaches the apikey-guarded endpoints over loopback: the shared
reconcile workflow's `curl` runs on the container host itself, inside the SSH
step that follows its VPN connection. Ad-hoc triggering from outside the network
is not available; an operator reaches these endpoints over LAN or VPN.

### Self-update (`project == "itsUP"`)

`GET /update-upstream/itsUP` triggers `_handle_itsup_update` (`:39-66`): in
`PYTHON_ENV=production` it **`git fetch origin main` + `git reset --hard
origin/main`** (destructive — discards local changes to the itsUP checkout),
then redeploys DNS + proxy stacks (`smart_deploy`) and `bin/itsup apply` (all
projects), then restarts the API. This is the unattended self-update path.

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
