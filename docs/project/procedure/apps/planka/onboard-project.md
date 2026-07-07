---
description: Create a new Planka project and board, and optionally onboard its initial member(s), as one flexible flow.
---
# Onboard A Planka Project — Procedure

## Goal

Stand up a new Planka project ready for use, including zero or more initial members, in one pass — without the human needing to know Planka's role model or its API shape to get there.

## Preconditions

- The agent has its own admin-role account (see `apps/planka/create-admin-account`).
- The human has named the project (and, if relevant, the person or people to add).

## Steps

1. **Create the project:** `POST /api/projects` with `{"name", "type": "shared"}`. Default to `type: "shared"` — it grants every instance admin automatic visibility into the project with **no** effect on any non-admin member's access (verified: the shared/private flag only gates the admin auto-visibility bypass in `projects/index.js`; `projectOwner`/`boardUser` see only what they're explicitly added to, regardless of type). Use `private` only if explicitly asked to keep it invisible to the other admin too.
2. **Create an initial board** inside it: `POST /api/projects/{id}/boards`.
3. **Branch: were one or more initial members named, or just the bare project?** If just the project, stop here.
4. **For each named person, ask one clarifying question rather than assuming a role** — the human should not need to already know Planka's model:
   - Should they be able to create and own their own projects later (`projectOwner`), or only ever work inside projects set up for them (`boardUser`)? Reserve global `admin` for instance operators only (you, the agent) — never assign it to a project member by default.
   - On this specific board, do they need to edit (`editor`) or only view/comment (`viewer`)?
5. **Check for an existing account first** (`GET /api/users`, match by email) before creating a new one — don't duplicate a person across projects.
6. For each new account: generate a password (`openssl rand -base64 24 | tr -d '/+='` — alphanumeric only, so it's always safe to embed unescaped in the JSON record below), create via `POST /api/users` with the chosen role, then add to the board via `POST /boards/{boardId}/board-memberships` with the chosen board role.
7. **Record all of them together** in one project-keyed secret — never one variable per person, since the project outlives whoever currently holds a seat on it:
   ```
   <PROJECT_NAME>_MEMBERS='[{"username":"...","password":"...","role":"...","email":"..."}, ...]'
   ```
   Append to this array on later runs rather than overwriting it.

## Outputs

- A project and board ready for use, with any named members added at the correct role.
- A project-keyed JSON credential record in the project's encrypted secrets file — see Recovery for its actual scope.

## Recovery

- **This credential record is an initial-bootstrap snapshot, not a live registry.** It reflects only the batch of people the agent added during infra-driven setup. The moment a `projectOwner` invites, removes, or resets someone directly through Planka's own UI, itsUP has no visibility into that change — the record goes stale for that person and is not corrected automatically. Don't treat it as authoritative for anyone added after initial setup.
- **Never authenticate as a stored member credential to act on that person's behalf.** It exists for recovery/support lookup only (e.g. "what was X's password" when they ask). The agent always acts as its own `agent` account; a human always acts as themselves.
- **Planka has no self-service password reset** (no "forgot password" email flow exists in Community edition as of writing — it's an open, unimplemented upstream feature request). The stored credential is not a convenience here, it's the only fallback that exists short of an admin manually resetting the account.
- Joint project ownership (a second `projectOwner`-level manager on one project) is Pro-gated in Community edition — a project has exactly one owner. Don't attempt it; board-level `editor` is the free-tier ceiling for a collaborator's access to a specific project.

## See Also

- docs/project/procedure/apps/planka/create-admin-account.md
