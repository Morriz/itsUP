---
delivered_by: [gated-file-endpoint]
description: Acceptance scenarios for the gated GET /file endpoint — it serves an allowlisted-extension local host file's bytes with a mapped content type, and refuses any non-allowlisted extension or missing path. Origin gating is the proxy's job, not the app's.
---

# Gated File Serving — Spec

## What it is

The itsUP management API exposes `GET /file?path=…`, which returns the bytes of a
local host file selected by path, constrained to an allowlisted set of file
extensions. The extension allowlist is the app-side security boundary given the
arbitrary path: it serves an approved format (starting with `.lsrules`) and never
a config or secret format. The boundary is enforced against the **resolved
target** — the path is resolved (following symlinks) first, and both the
extension check and the bytes served are that resolved target's, so a
`.lsrules` symlink pointing at a prohibited file cannot leak it. The endpoint carries no authentication — the origin
gate that restricts who may reach it over the internet lives at the proxy as a
route-scoped source-IP allowlist
(`project/spec/feature/deployment/route-scoped-ip-allowlist`), not in the app.

The business value is provisioning files to HTTPS-only, header-less consumers
(the driver is Little Snitch `.lsrules` subscriptions) that reject `file://`
references and cannot carry a URL secret — they receive a stable HTTPS URL whose
bytes and content type they can consume directly.

### Use cases

The scenarios below are bound by functional tests in
`tests/functional/api/test_gated_file_endpoint.py`, which drive the FastAPI app
through its ASGI boundary with a `TestClient` against real files on disk.

#### UC-GFS1: An allowlisted-extension file is served with its bytes and content type

```gherkin
Given a local file whose resolved target's extension is in the allowlist
When GET /file is requested with that file's path
Then the response status is 200
And the response body is the resolved target's exact bytes
And the response content type is the type mapped for that extension
```

#### UC-GFS2: A non-allowlisted extension is refused

```gherkin
Given a local file whose extension is not in the allowlist
When GET /file is requested with that file's path
Then the response is refused with a client-error status
And no file bytes are returned
```

#### UC-GFS3: A missing or non-regular-file path is refused

```gherkin
Given a path that does not resolve to an existing regular file
When GET /file is requested with that path
Then the response is refused with a client-error status
```

#### UC-GFS4: A symlink whose resolved target is a non-allowlisted file is refused

```gherkin
Given an allowlisted-extension path that is a symlink resolving to a prohibited-extension file
When GET /file is requested with that symlink's path
Then the response is refused with a client-error status
And none of the target file's bytes are returned
```

## Canonical fields

- Endpoint: `GET /file?path=<host-path>` on the API app (`api/main.py`),
  unauthenticated at the app; served over `:8888` behind the proxy.
- Security boundary: a positive extension allowlist (initially `{.lsrules}`,
  extended by editing the set), enforced against the **resolved target** (the
  path is resolved through symlinks before the extension and regular-file checks,
  and only the resolved target's bytes are served). Because it is positive,
  config/secret formats (`.json/.yml/.yaml/.env/.pem/.key/.conf`) are refused by
  construction — including via a symlink whose target carries a prohibited
  extension.
- Content type: mapped per allowed extension (`.lsrules` is JSON).
- Refusals: missing `path`, non-allowlisted extension, and paths that are not an
  existing regular file each return a client-error status via `HTTPException`.
- Origin gating: enforced at the proxy (route-scoped source-IP allowlist), not by
  the endpoint. The public `/redirect` bouncer is a separate, unauthenticated,
  ungated route and is unaffected.

## See Also

- docs/project/spec/api-surface.md
- docs/project/spec/feature/deployment/route-scoped-ip-allowlist.md
