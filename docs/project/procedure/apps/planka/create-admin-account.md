---
description: Create a dedicated (non-shared-identity) admin account on a self-hosted Planka instance via its REST API.
---
# Create A Planka Admin Account — Procedure

## Goal

Give an agent its own attributable admin account on a Planka instance, not tied to any one AI agent by name, instead of reusing the human's `DEFAULT_ADMIN_*` bootstrap identity. Planka's web admin panel (instance-wide user/project management UI) is a paid Pro feature — the free tier's only path to this is the REST API.

## Preconditions

- Planka instance is up and reachable.
- The bootstrap admin credentials (`DEFAULT_ADMIN_EMAIL`/`DEFAULT_ADMIN_USERNAME` + `DEFAULT_ADMIN_PASSWORD`) are known — they are the project's own secrets, loaded per `project/spec/secrets-management`.

## Steps

1. Authenticate as the bootstrap admin: `POST /api/access-tokens` with `{"emailOrUsername": "<DEFAULT_ADMIN_USERNAME>", "password": "<DEFAULT_ADMIN_PASSWORD>"}`. Extract `item` as the bearer token.
2. Generate a fresh random password (`openssl rand -base64 24 | tr -d '/+='`) — alphanumeric only, never reused or hand-picked. This isn't just hygiene: it's what makes the credential safe to embed unescaped in JSON or any delimiter-based record later.
3. Create the account with agent-agnostic identity (username/email like `agent`/`agent@<domain>`, never a specific agent's name — the account outlives any one AI): `POST /api/users` with the bearer token, body `{"email", "password", "name", "username", "role": "admin"}`. `role` is mandatory — omitting it 400s.
4. Attempt a login as the new account. It will 403 with `step: "accept-terms"` — this is expected on first use, not a failure. Ask the human to complete the terms-acceptance screen once via the web UI (the endpoint's `signature` requirement is a client-side hash of the terms content, not practically reproducible via the API — don't burn time trying).
5. Re-attempt login after confirmation; it now succeeds and returns a normal token.
6. **Persist the new credential in the project's secrets store immediately** (`secrets/<project>.txt`, encrypt with `itsup encrypt <project> --delete`) — never leave it only in a chat transcript or session output. Note that `PATCH /api/users/:id` silently no-ops on `username`/`email` when changing another account's identity — to rename an existing agent account, delete and recreate it rather than trying to patch it.

## Outputs

- A dedicated Planka account, admin-role, credential recorded in the project's encrypted secrets file.

## Recovery

- If step 4 stalls (human hasn't completed the browser step), don't keep guessing at the `signature` algorithm — it's a client-side hash of the terms content, not a documented API contract. Wait for confirmation instead.

## See Also

- docs/project/procedure/apps/planka/onboard-project.md
