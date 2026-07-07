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

**Credential boundary: steps 1–3 use the human owner's token, everything from step 4 onward uses the agent's own token.** Project ownership and the board-creation auto-membership both bind to whoever's credentials make those specific calls (see step 2) — so the human's token is required for those three calls, and only those. Continuing to reuse the human's credentials past that point is not needed and not done; the agent has its own admin account precisely so it doesn't have to borrow the human's identity for routine work.

1. **Create the project:** `POST /api/projects` with `{"name", "type": "shared"}` (the `type` field is required to create a project at all; `"shared"` vs `"private"` is accepted by the API, but empirically does **not** grant an admin automatic visibility into the project it wasn't otherwise added to — confirmed by testing the agent account's own project listing on a `shared` project it wasn't a member of: empty, until explicitly added. Don't trust the `projects/index.js` admin-bypass code path at face value; it does not appear to produce visible results in practice on this deployment. Treat `type` as required-but-inert until this is re-verified against a newer Planka version).
2. **Create an initial board** inside it: `POST /api/projects/{id}/boards`. Whoever's credentials made this call is auto-added as a board `editor` as a side effect — that's Planka's own behavior, not something the agent has to do manually. This is why the human onboarding the project (if their own token is used) needs no separate step, but the agent does:
3. **Add the agent's own account as a board member too** (`POST /boards/{boardId}/board-memberships`, `role: "editor"`) — the agent's identity is never the one that called steps 1–2 (a human's admin token is), so it does not get the auto-membership above and must add itself explicitly. Do this even if the human didn't ask for it; without it, the agent loses access to a project it just helped create.
4. **A new board has no working lists** — only Planka's own `archive`/`trash` system lists, neither meant for active cards. Ask the human what list/lane structure they want, offering a sensible default rather than an open-ended question: "To Do / In Progress / Done" (`POST /boards/{boardId}/lists`, `type: "active"`, sequential `position`) covers most small/personal-scale boards. Only build something more elaborate (swimlanes, a different stage count) if asked.
5. **Branch: were one or more initial members named, or just the bare project?** If just the project, stop here.
6. **For each named person, ask one clarifying question rather than assuming a role** — the human should not need to already know Planka's model:
   - Should they be able to create and own their own projects later (`projectOwner`), or only ever work inside projects set up for them (`boardUser`)? Reserve global `admin` for instance operators only (you, the agent) — never assign it to a project member by default.
   - On this specific board, do they need to edit (`editor`) or only view/comment (`viewer`)?
7. **Check for an existing account first** (`GET /api/users`, match by email) before creating a new one — don't duplicate a person across projects.
8. For each new account: generate a password (`openssl rand -base64 24 | tr -d '/+='` — alphanumeric only, so it's always safe to embed unescaped in the JSON record below), create via `POST /api/users` with the chosen role, then add to the board via `POST /boards/{boardId}/board-memberships` with the chosen board role.
9. **Record all of them together** in one project-keyed secret — never one variable per person, since the project outlives whoever currently holds a seat on it:
   ```
   <PROJECT_NAME>_MEMBERS='[{"username":"...","password":"...","role":"...","email":"..."}, ...]'
   ```
   Append to this array on later runs rather than overwriting it.

## Outputs

- A project and board with a real working list structure (not just Planka's system lists), the agent included as a board member, and any named members added at the correct role.
- A project-keyed JSON credential record in the project's encrypted secrets file — see Recovery for its actual scope.

## Recovery

- **This credential record is an initial-bootstrap snapshot, not a live registry.** It reflects only the batch of people the agent added during infra-driven setup. The moment a `projectOwner` invites, removes, or resets someone directly through Planka's own UI, itsUP has no visibility into that change — the record goes stale for that person and is not corrected automatically. Don't treat it as authoritative for anyone added after initial setup.
- **Never authenticate as a stored member credential to act on that person's behalf.** It exists for recovery/support lookup only (e.g. "what was X's password" when they ask). The agent always acts as its own `agent` account; a human always acts as themselves.
- **Planka has no self-service password reset** (no "forgot password" email flow exists in Community edition as of writing — it's an open, unimplemented upstream feature request). The stored credential is not a convenience here, it's the only fallback that exists short of an admin manually resetting the account.
- Joint project ownership (a second `projectOwner`-level manager on one project) is Pro-gated in Community edition — a project has exactly one owner. Don't attempt it; board-level `editor` is the free-tier ceiling for a collaborator's access to a specific project.
- The agent's global `admin` role does **not** let it add board memberships on a project it isn't the manager of — confirmed by testing: the agent's own token, despite already holding board membership, gets `E_NOT_FOUND` calling `board-memberships/create` on a project it doesn't manage. `board-memberships/create.js`'s project-manager gate has no admin bypass, unlike the self-vs-others restriction on the same endpoint. This is why step 3 must run on the human owner's token, not the agent's — there is no shortcut.

## See Also

- docs/project/procedure/apps/planka/create-admin-account.md
