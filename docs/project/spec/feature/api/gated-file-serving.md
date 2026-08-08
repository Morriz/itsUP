---
description: Acceptance scenarios for the gated GET /file endpoint — it serves an
  allowlisted-extension local host file's bytes with a mapped content type, and refuses
  any non-allowlisted extension or missing path. Origin gating is the proxy's job,
  not the app's.
---

# Gated File Serving — Spec

## What it is

The itsUP management API exposes `GET /file?path=…`, which returns the bytes of a
local host file selected by path, constrained to an allowlisted set of file
extensions. The extension allowlist is the app-side security boundary given the
arbitrary path: it serves an approved format (starting with `.lsrules`) and never
a config or secret format. The endpoint carries no authentication — the origin
gate that restricts who may reach it over the internet lives at the proxy as a
route-scoped source-IP allowlist
(`project/spec/feature/deployment/route-scoped-ip-allowlist`), not in the app.

The business value is provisioning files to HTTPS-only, header-less consumers
(the driver is Little Snitch `.lsrules` subscriptions) that reject `file://`
references and cannot carry a URL secret — they receive a stable HTTPS URL whose
bytes and content type they can consume directly.

<!-- planned:lsrules-upload-endpoint -->

The capability has two halves. The read half selects a file already on the host;
the write half puts one there. Files the consumer needs are generated on a
producer machine rather than on the host, so without the write half the read
half can only serve what happens to be present locally — which for a
dynamically generated rule group is nothing. `PUT /upload/{name}` closes that
gap: an authenticated producer stores the bytes under a name the host owns, and
the existing read path serves them at a URL that stays stable across
regenerations.

<!-- /planned:lsrules-upload-endpoint -->

The vendor contract the read half answers to is recorded in
`third-party/little-snitch/rule-group-subscriptions`: publication over HTTPS is
mandatory, the subscriber owns the refresh interval, and no content-type,
disposition, or caching contract is specified. The validators the response does
carry come from the serving framework and are described in
`third-party/starlette/fileresponse-caching-headers`.

### Use cases

The scenarios below are bound by functional tests in
`tests/api/test_gated_file_endpoint.py`, which drive the FastAPI app
through its ASGI boundary with a `TestClient` against real files on disk.

#### UC-GFS1: An allowlisted-extension file is served with its bytes and content type

```gherkin
Given a local file whose extension is in the allowlist
When GET /file is requested with that file's path
Then the response status is 200
And the response body is the file's exact bytes
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
Given a path that is not an existing regular file
When GET /file is requested with that path
Then the response is refused with a client-error status
```

<!-- planned:lsrules-upload-endpoint -->

#### UC-GFS4: An authenticated upload of an allowlisted file is stored and then served

```gherkin
Given a producer holding the API key
When it uploads a file whose extension is in the allowlist, naming it within the upload directory
Then the response reports the stored file's location
And a subsequent GET /file for that location returns the uploaded bytes
```

#### UC-GFS5: An unauthenticated upload is refused

```gherkin
Given a producer presenting no API key or a wrong one
When it uploads a file whose extension is in the allowlist
Then the response is refused as unauthorized
And no file is created
```

#### UC-GFS6: An upload whose extension is not allowlisted is refused

```gherkin
Given a producer holding the API key
When it uploads a file whose extension is not in the allowlist
Then the response is refused with a client-error status
And no file is created
```

#### UC-GFS7: Re-uploading a name replaces the served bytes at an unchanged URL

```gherkin
Given an allowlisted file previously uploaded under a name
When a producer holding the API key uploads different bytes under that same name
Then a GET /file for the unchanged location returns the new bytes
And the cache validator of that response differs from the one served before the upload
```

#### UC-GFS8: An upload name that escapes the owned directory is refused

```gherkin
Given a producer holding the API key
When it uploads a file under a name that is not a single path segment within the upload directory
Then the response is refused with a client-error status
And no file is created outside the upload directory
```

#### UC-GFS9: An upload larger than the accepted size is refused before it is stored

```gherkin
Given a producer holding the API key
When it uploads a body larger than the accepted maximum
Then the response is refused with a client-error status
And no file is created
```

<!-- /planned:lsrules-upload-endpoint -->

## Canonical fields

- Endpoint: `GET /file?path=<host-path>` on the API app (`api/main.py`),
  unauthenticated at the app; served over `:8888` behind the proxy.
- Security boundary: a positive extension allowlist (initially `{.lsrules}`,
  extended by editing the set). Because it is positive, config/secret formats
  (`.json/.yml/.yaml/.env/.pem/.key/.conf`) are refused by construction.
- Content type: mapped per allowed extension (`.lsrules` is JSON).
- Refusals: a non-allowlisted extension and a path that is not an existing
  regular file each return a client-error status via `HTTPException`. These are
  the endpoint's only refusals. `path` is a required query parameter; omitting
  it is rejected by FastAPI's own request validation at the framework boundary,
  not by endpoint-specific handling.
- Origin gating: enforced at the proxy (route-scoped source-IP allowlist), not by
  the endpoint. The public `/redirect` bouncer is a separate, unauthenticated,
  ungated route and is unaffected.

<!-- planned:lsrules-upload-endpoint -->

### Upload endpoint

- Endpoint: `PUT /upload/{name}` on the same API app, guarded by the API key
  (`verify_apikey`) exactly as the other mutating endpoints are. The request body
  is the file's raw bytes.
- Gating is asymmetric by design. Both sides sit behind the same LAN-origin
  allowlist at the proxy, so neither is reachable from the internet. They differ
  at the app: the read side is unauthenticated because its consumer is a
  header-less subscription fetcher that cannot carry a secret, while the write
  side is authenticated because its caller is a script or agent that can. The
  allowlist is never the write's authorisation — it scopes the network, and an
  origin is not a credential.
- The host owns the destination; the request supplies only a name within it.
  `name` must be a single path segment — a value carrying a directory separator,
  a parent reference, or an absolute path is refused, and the resolved
  destination is confirmed to lie inside the upload directory before anything is
  written. A caller-supplied destination would be a remote arbitrary-write
  primitive on the host that holds the SOPS age key.
- The upload directory is resolved through the install root, so its location
  follows `ITSUP_ROOT` like every other itsUP-owned tree. Its contents are
  regenerable host state and are not tracked in the repository.
- The extension allowlist is the same set the read side enforces, so the write
  boundary can never be looser than the read boundary it feeds.
- The accepted body size is bounded at 1 MB, and the bound is enforced as the
  body is read rather than after it is buffered, so an oversized request is
  refused without being held in memory or reaching disk. The bound exists to
  keep an authenticated write from exhausting host memory or disk, not to
  police content size — it sits well above any rule group while still being a
  hard ceiling.
- The caller names the file, and that name is what pins its served URL. Writing
  a name that already exists replaces its contents, leaving the URL unchanged —
  which is what keeps a subscription working across regenerations. Because the
  served response's cache validator derives from the file's modification time
  and size, a replacement changes the validator, so a client holding a cached
  copy sees a changed resource.
- Replacement is the contract, so the endpoint cannot distinguish a re-upload of
  one logical file from a different file that chose the same name. Keeping
  distinct rule groups apart is the caller's naming discipline; a single path
  segment still admits any distinguishing prefix. What the endpoint does
  guarantee is that no name reaches a location outside the upload directory.
- The response reports the stored file's location, so a producer can construct
  the `GET /file?path=…` URL without knowing the install root.
- The route is published on the same hostname as the read endpoint and carries
  the same LAN-origin allowlist, so an upload travels over HTTPS and only from
  the local network. The API key is a second, independent boundary: the origin
  gate attributes every hairpinned LAN client to the gateway address and so
  cannot tell one LAN device from another, and a write earns a credential that
  an origin cannot supply. See `project/spec/api-surface`.

<!-- /planned:lsrules-upload-endpoint -->

## See Also

- docs/project/spec/api-surface.md
- docs/project/spec/feature/deployment/route-scoped-ip-allowlist.md
