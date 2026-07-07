---
description: Create a new Planka project, its board, and its one mandatory initial member.
---
# Onboard A Planka Project — Procedure

## Goal

Stand up a new Planka project ready for use, with the one person it's being set up for already able to work on it, in one pass — without the human needing to know Planka's role model or its API shape to get there.

## Preconditions

- The agent has its own admin-role account (see `apps/planka/create-admin-account`).
- The human has named the project and who its initial member is — a project is not considered onboarded without one; there is no owner-only project.

## Steps

**Credential boundary: steps 1–3 use the human operator's own credentials, everything from step 4 onward uses the agent's own token.** Project ownership and the board-creation auto-membership both bind to whoever's credentials make those specific calls, and the human operator is always, permanently, the technical owner of every project they create — there is no ownership transfer, no per-project ownership question, and no scenario where anyone else becomes the owner instead. The agent has its own admin account precisely so it doesn't have to borrow anyone's identity for routine work past project setup.

1. **Create the project**, using the human operator's own credentials: `POST /api/projects` with `{"name", "type": "shared"}` (the `type` field is required to create a project at all; `"shared"` vs `"private"` is accepted by the API, but empirically does **not** grant an admin automatic visibility into the project it wasn't otherwise added to — confirmed by testing the agent account's own project listing on a `shared` project it wasn't a member of: empty, until explicitly added. Don't trust the `projects/index.js` admin-bypass code path at face value; it does not appear to produce visible results in practice on this deployment. Treat `type` as required-but-inert until this is re-verified against a newer Planka version).
2. **Create an initial board** inside it, same credentials: `POST /api/projects/{id}/boards`. Whoever's credentials made this call is auto-added as a board `editor` as a side effect — that's Planka's own behavior, not something the agent has to do manually. This is why the human operator needs no separate membership step, but the agent does:
3. **Add the agent's own account as a board member too**, still the human operator's credentials: `POST /boards/{boardId}/board-memberships`, `role: "editor"` — the agent's identity is never the one that called steps 1–2, so it does not get the auto-membership above and must be added explicitly. Do this even if not asked; without it, the agent loses access to a project it just helped create.
4. **A new board has no working lists** — only Planka's own `archive`/`trash` system lists, neither meant for active cards. Ask what list/lane structure is wanted, offering a sensible default rather than an open-ended question: "To Do / In Progress / Done" (`POST /boards/{boardId}/lists`, `type: "active"`, sequential `position`) covers most small/personal-scale boards. Only build something more elaborate (swimlanes, a different stage count) if asked.
5. **Check for an existing account first** for the named initial member (`GET /api/users`, match by email) before creating a new one — don't duplicate a person across projects.
6. **If new, create the account with a fixed role — not asked, not defaulted-and-upgraded:** `globalRole: "projectOwner"`. This is mandatory for every project's initial member; it is not a choice between `projectOwner` and `boardUser` made per person. (`admin` is reserved for instance operators only — never assigned to a project member.) Generate the password with `openssl rand -base64 24 | tr -d '/+='` — alphanumeric only, so it's always safe to embed unescaped in the JSON record below.
7. **Add them to the board with a fixed board role, also not asked:** `boardRole: "editor"` (`POST /boards/{boardId}/board-memberships`, `role: "editor"`) — this is the person the project exists for; they need full working access by definition.
8. **Record the credential** in one project-keyed secret, both role fields kept separate since they answer genuinely different questions — `globalRole` governs whether this person can self-serve create their *own*, separate projects elsewhere; `boardRole` governs what they can do on *this* board. Neither implies the other: a `projectOwner` with no board membership has zero access to this project, and board access is what actually lets them work here.
   ```
   <PROJECT_NAME>_MEMBERS='[{"username":"...","password":"...","globalRole":"projectOwner","boardRole":"editor","email":"..."}]'
   ```
   If a project later needs more people beyond this one mandatory initial member, that's a separate, smaller operation (add an existing-or-new account to the board, append to this same array) — not a re-run of this procedure, and not necessarily the same fixed roles; ask what's needed at that point.

## Outputs

- A project and board with a real working list structure (not just Planka's system lists), the agent included as a board member, and the initial member able to work on it.
- A project-keyed JSON credential record in the project's encrypted secrets file — see Recovery for its actual scope.

## Recovery

- **This credential record is an initial-bootstrap snapshot, not a live registry.** It reflects only the people the agent added during infra-driven setup. The moment someone invites, removes, or resets another account directly through Planka's own UI, the agent has no visibility into that change — the record goes stale for that person and is not corrected automatically. Don't treat it as authoritative for anyone added after initial setup.
- **Never authenticate as a stored member credential to act on that person's behalf.** It exists for recovery/support lookup only (e.g. "what was X's password" when they ask). The agent always acts as its own `agent` account; a human always acts as themselves.
- **Planka has no self-service password reset** (no "forgot password" email flow exists in Community edition as of writing — it's an open, unimplemented upstream feature request). The stored credential is not a convenience here, it's the only fallback that exists short of an admin manually resetting the account.
- Joint project ownership (a second `projectOwner`-role manager on one project) is Pro-gated in Community edition — a project has exactly one owner, permanently the human operator who created it. Don't attempt to change or transfer it; board-level `editor` is the free-tier ceiling for anyone else's access to a specific project.
- The agent's global `admin` role does **not** let it add board memberships on a project it isn't the manager of — confirmed by testing: the agent's own token, despite already holding board membership, gets `E_NOT_FOUND` calling `board-memberships/create` on a project it doesn't manage. `board-memberships/create.js`'s project-manager gate has no admin bypass, unlike the self-vs-others restriction on the same endpoint. This is why step 3 must run on the human operator's token, not the agent's — there is no shortcut.

## See Also

- ~/.teleclaude/docs/apps/procedure/planka/create-admin-account.md
