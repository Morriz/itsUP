---
description: Create a new Planka project and board, and optionally onboard its initial member(s), as one flexible flow.
---
# Onboard A Planka Project — Procedure

## Goal

Stand up a new Planka project ready for use, including zero or more initial members, in one pass — without the human needing to know Planka's role model or its API shape to get there.

## Preconditions

- The agent has its own admin-role account (see `apps/planka/create-admin-account`).
- The human has named the project.

## Steps

**Credential boundary: steps 2–4 use the project owner's token, everything from step 5 onward uses the agent's own token.** Project ownership and the board-creation auto-membership both bind to whoever's credentials make those specific calls — so the owner's token is required for those three calls, and only those. The agent has its own admin account precisely so it doesn't have to borrow anyone's identity for routine work past that point.

1. **Ask who will own the project — always, every time, never assumed.** Ownership binds to whoever's credentials create the project; there is exactly one owner per project (Community edition is single-owner, see Recovery), fixed at creation. This is a separate question from anything about other members below — it is not optional and has no default.
2. **Create the project**, using the owner's credentials: `POST /api/projects` with `{"name", "type": "shared"}` (the `type` field is required to create a project at all; `"shared"` vs `"private"` is accepted by the API, but empirically does **not** grant an admin automatic visibility into the project it wasn't otherwise added to — confirmed by testing the agent account's own project listing on a `shared` project it wasn't a member of: empty, until explicitly added. Don't trust the `projects/index.js` admin-bypass code path at face value; it does not appear to produce visible results in practice on this deployment. Treat `type` as required-but-inert until this is re-verified against a newer Planka version).
3. **Create an initial board** inside it, same owner's credentials: `POST /api/projects/{id}/boards`. Whoever's credentials made this call is auto-added as a board `editor` as a side effect — that's Planka's own behavior, not something the agent has to do manually. This is why the owner needs no separate membership step, but the agent does:
4. **Add the agent's own account as a board member too**, still the owner's credentials: `POST /boards/{boardId}/board-memberships`, `role: "editor"` — the agent's identity is never the one that called steps 2–3, so it does not get the auto-membership above and must be added explicitly. Do this even if not asked; without it, the agent loses access to a project it just helped create.
5. **A new board has no working lists** — only Planka's own `archive`/`trash` system lists, neither meant for active cards. Ask what list/lane structure is wanted, offering a sensible default rather than an open-ended question: "To Do / In Progress / Done" (`POST /boards/{boardId}/lists`, `type: "active"`, sequential `position`) covers most small/personal-scale boards. Only build something more elaborate (swimlanes, a different stage count) if asked.
6. **Branch: were one or more additional members named, or just the owner?** If just the owner, stop here.
7. **For each named person, two independent questions — default to the lesser privilege on both, upgrade only if asked:**
   - Default `boardUser` (works only inside projects set up for them). Only assign `projectOwner` if this person should also be able to create and own their own, separate projects later — that capability has nothing to do with ownership of the current project, which is already fixed by step 1. Reserve global `admin` for instance operators (the agent) — never assign it to a project member.
   - Default is asked, not assumed: `editor` (can create/edit/move cards and lists) or `viewer` (read-only, optionally can comment) on this board.
8. **Check for an existing account first** (`GET /api/users`, match by email) before creating a new one — don't duplicate a person across projects.
9. For each new account: generate a password (`openssl rand -base64 24 | tr -d '/+='` — alphanumeric only, so it's always safe to embed unescaped in the JSON record below), create via `POST /api/users` with the chosen role, then add to the board via `POST /boards/{boardId}/board-memberships` with the chosen board role.
10. **Record all of them together** in one project-keyed secret — never one variable per person, since the project outlives whoever currently holds a seat on it:
   ```
   <PROJECT_NAME>_MEMBERS='[{"username":"...","password":"...","role":"...","email":"..."}, ...]'
   ```
   Append to this array on later runs rather than overwriting it.

## Outputs

- A project and board with a real working list structure (not just Planka's system lists), the agent included as a board member, and any named members added at the correct role.
- A project-keyed JSON credential record in the project's encrypted secrets file — see Recovery for its actual scope.

## Recovery

- **This credential record is an initial-bootstrap snapshot, not a live registry.** It reflects only the batch of people the agent added during infra-driven setup. The moment a `projectOwner` invites, removes, or resets someone directly through Planka's own UI, the agent has no visibility into that change — the record goes stale for that person and is not corrected automatically. Don't treat it as authoritative for anyone added after initial setup.
- **Never authenticate as a stored member credential to act on that person's behalf.** It exists for recovery/support lookup only (e.g. "what was X's password" when they ask). The agent always acts as its own `agent` account; a human always acts as themselves.
- **Planka has no self-service password reset** (no "forgot password" email flow exists in Community edition as of writing — it's an open, unimplemented upstream feature request). The stored credential is not a convenience here, it's the only fallback that exists short of an admin manually resetting the account.
- Joint project ownership (a second `projectOwner`-level manager on one project) is Pro-gated in Community edition — a project has exactly one owner. Don't attempt it; board-level `editor` is the free-tier ceiling for a collaborator's access to a specific project.
- The agent's global `admin` role does **not** let it add board memberships on a project it isn't the manager of — confirmed by testing: the agent's own token, despite already holding board membership, gets `E_NOT_FOUND` calling `board-memberships/create` on a project it doesn't manage. `board-memberships/create.js`'s project-manager gate has no admin bypass, unlike the self-vs-others restriction on the same endpoint. This is why step 4 must run on the owner's token, not the agent's — there is no shortcut.

## See Also

- ~/.teleclaude/docs/apps/procedure/planka/create-admin-account.md
