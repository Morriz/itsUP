---
description: Verified Starlette FileResponse header behavior the itsUP gated-file endpoint inherits — the ETag derived from (st_mtime, st_size), the Content-Length and Last-Modified validators, and the opt-in Content-Disposition that only appears when a filename is passed.
---

# Starlette — `FileResponse` caching and disposition headers

## What it is

itsUP's `GET /file` endpoint returns a `fastapi.responses.FileResponse`, which is
Starlette's `FileResponse` (`api/main.py`). The response headers a subscriber
sees are therefore Starlette's, not itsUP's — itsUP passes only `path` and
`media_type` today. This snippet records what that class emits, because two of
the gated-file capability's acceptance criteria describe client caching and
file-versus-inline delivery, and both are decided here.

Verified by reading the installed package at
`.venv/lib/python3.14/site-packages/starlette/responses.py` (class `FileResponse`,
`__init__` and `set_stat_headers`).

## Validators emitted on every response

`set_stat_headers()` stats the file and sets three headers, each via
`setdefault` (so an explicitly passed header wins):

| Header | Value |
|---|---|
| `content-length` | `st_size` |
| `last-modified` | `st_mtime`, RFC-formatted GMT |
| `etag` | `"<md5 of f"{st_mtime}-{st_size}">"` |

**The ETag is keyed on modification time *and* size — not on content.** Two
consequences follow directly:

- Rewriting the file with **identical bytes** still changes `st_mtime`, so the
  ETag changes and a conditional client re-fetches. The validator is not a
  content hash.
- Changing content **without** changing size still changes `st_mtime`, so the
  ETag changes. A re-fetch is therefore *not* gated on the byte size changing;
  size is only one of the two inputs.

`accept-ranges: bytes` is also set, and `If-Range` is honored against either the
`last-modified` or the `etag` value.

## `Content-Disposition` is opt-in

`FileResponse.__init__` sets `content-disposition` **only when a `filename`
argument is passed**. Its `content_disposition_type` parameter defaults to
`"attachment"`, and the header is rendered as
`attachment; filename="<name>"` — or `attachment; filename*=utf-8''<encoded>`
when the name needs percent-encoding.

Passing no `filename` — itsUP's current call — emits **no** `content-disposition`
header at all, so a browser decides for itself whether to display or download.
Making a response arrive as a downloaded file is therefore a one-argument change,
not a new mechanism.

## `media_type` resolution

When `media_type` is not supplied, Starlette guesses it from `filename or path`
and falls back to `application/octet-stream`. itsUP supplies `media_type`
explicitly from its extension allowlist, so the guess never runs on this path.

## Sources

- [Starlette responses documentation](https://www.starlette.io/responses/)
- [Starlette `responses.py` source (`class FileResponse`)](https://github.com/encode/starlette/blob/master/starlette/responses.py)
