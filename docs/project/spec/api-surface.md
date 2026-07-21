---
description: 'The itsUP management REST API — apikey-guarded webhook endpoints that trigger deploys (including a production self-update that hard-resets to origin/main) and list projects.'
---

# API Surface — Spec

## What it is

A small FastAPI app (`api/main.py`, title `itsUP API` v2.0) that lets external
systems trigger deploys via webhook and query projects. It is **not**
<!-- planned-change:verifiable-deploy-chain -->
containerized — it runs as a host process on `:8888` (`bin/start-api.sh`) and is
exposed through Traefik like any external-host project.
<!-- change:verifiable-deploy-chain -->
containerized — it runs as a host process on `:8888`, supervised by the
`itsup-api.service` systemd unit on Linux hosts (`Restart=on-failure`; see
`project/spec/runtime-operations`) and started by `bin/start-api.sh` elsewhere,
and is exposed through Traefik like any external-host project.
<!-- /planned-change:verifiable-deploy-chain -->
Every mutating/data
endpoint is guarded by an API key (`verify_apikey`, `lib/auth.py`, via FastAPI
`Depends`). Deploy work runs in a FastAPI `BackgroundTask`; the endpoint returns
immediately.

## Canonical fields

### Endpoints (`api/main.py`)

| Method/Path | Auth | Behaviour |
|-------------|------|-----------|
| `GET /update-upstream/{project}` | apikey | Background-deploys one project via `bin/itsup apply {project}` (`:27-36,84-93`). Unknown project ⇒ logged and ignored. |
| `GET /update-upstream/{project}/{service}` | apikey | Same, scoped to one service. |
| `POST /reconcile` | apikey | Background full-stack reconcile: pulls the `projects`/`secrets` config repos then runs `itsup apply`; single-flight with trailing-run coalescing (`lib/reconcile.py`). |
| `GET /projects` | apikey | Returns `list_projects()` (`@cache`d, `:96-100`). |
<!-- planned:verifiable-deploy-chain -->
| `GET /health` | none | Liveness probe: returns `200` with a static ok body. Carries no data and reads no state; probed by `pi-healthcheck` on `localhost:8888` and by the scheduled reconcile workflow through Traefik. |
<!-- /planned:verifiable-deploy-chain -->
| `GET /redirect?url=` | none | 307-redirects, but **only** `message://` / `imessage://` schemes; rejects other schemes or whitespace (`:103-116`). |

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
