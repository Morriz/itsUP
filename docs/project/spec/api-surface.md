---
id: 'project/spec/api-surface'
type: 'spec'
scope: 'project'
description: 'The itsUP management REST API — apikey-guarded webhook endpoints that trigger deploys (including a production self-update that hard-resets to origin/main) and list projects.'
generated_by: 'telec-init'
generated_at: '2026-06-11 00:00:00+00:00'
---

# API Surface — Spec

## What it is

A small FastAPI app (`api/main.py`, title `itsUP API` v2.0) that lets external
systems trigger deploys via webhook and query projects. It is **not**
containerized — it runs as a host process on `:8888` (`bin/start-api.sh`) and is
exposed through Traefik like any external-host project. Every mutating/data
endpoint is guarded by an API key (`verify_apikey`, `lib/auth.py`, via FastAPI
`Depends`). Deploy work runs in a FastAPI `BackgroundTask`; the endpoint returns
immediately.

## Canonical fields

### Endpoints (`api/main.py`)

| Method/Path | Auth | Behaviour |
|-------------|------|-----------|
| `GET /update-upstream/{project}` | apikey | Background-deploys one project via `bin/itsup apply {project}` (`:27-36,84-93`). Unknown project ⇒ logged and ignored. |
| `GET /update-upstream/{project}/{service}` | apikey | Same, scoped to one service. |
| `GET /projects` | apikey | Returns `list_projects()` (`@cache`d, `:96-100`). |
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

- docs/stacks/api.md
- docs/project/design/deployment-orchestration.md
