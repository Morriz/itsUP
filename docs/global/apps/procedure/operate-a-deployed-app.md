---
description: Single entry point for operating any already-deployed app — recognize the app, pull whatever knowledge exists for it, then act or ask.
activation_trigger: Asked to perform any administrative, configuration, maintenance, troubleshooting, or upgrade task on a specific application already running in the fleet — user/access management, backup or restore, diagnosing a failure, applying a version change, or any other operational task against a live instance. Not while first deploying a new app.
---
# Operate A Deployed App — Procedure

## Goal

Give every "do something with app X" request a single, mechanical entry point, so an agent never has to already know per-app quirks in advance and never re-discovers the same thing twice — from any project, any machine, since this knowledge is published globally rather than locked to one repo. This is the *only* activation-triggered snippet in the `apps` domain — everything else underneath it is found by executing these steps, not by matching its own trigger phrase.

## Preconditions

- The request names or clearly implies a specific already-running app.
- The agent has (or can get) access to that app's owning repo — this procedure finds the *knowledge* from anywhere, but acting on it still requires whatever GitOps/secrets access the owning fleet requires (e.g. itsUP's own `projects/`/`secrets/` for apps it operates).

## Steps

1. **Identify the app and its owning fleet.** If unclear which repo operates it, ask — don't guess. For itsUP-operated apps: list `projects/` in that repo and match the request against a real slug.
2. **Pull the index:** `telec docs index --domains apps` — if the CLI rejects `apps` as an unrecognized domain (a known lag in the domain-filter's own value list, unrelated to whether the domain is actually published), fall back to `telec docs index --scope global` and grep the ids for the `apps/` prefix instead. Don't conclude the domain is missing just because this one flag errors — verify with the fallback before assuming.
3. **Filter for the app's slug** as a path segment in the returned ids (e.g. `apps/procedure/planka/...`), regardless of taxonomy type (spec, procedure, whatever fits).
4. **Fetch every match:** `telec docs get <id1> <id2> ...`. If there are no matches, there's no prior knowledge for this app yet — proceed carefully on general knowledge, and consider authoring a snippet afterward if you learn something non-obvious worth keeping (see `general/procedure/doc-snippet-authoring`).
5. **Decide.** If the fetched knowledge (plus the request) is enough to act confidently, act. If something material is still ambiguous, ask — don't fill the gap with a guess.

## Outputs

- Full available context on the target app loaded before the first live action against it, in one pass.

## Recovery

- If step 3 turns up matches split across multiple taxonomy types for the same app (a `spec` and a `procedure` both under `apps/<slug>/`), read all of them — they're complementary, not redundant.

## Discipline

The failure mode this guards against: either acting on a per-app request from memory/pattern-matching alone (re-discovering a quirk someone already paid to learn), or, at the other extreme, scattering activation triggers across every individual per-app snippet — which would bloat every project's "Activatable Procedures" listing with one entry per app-and-task combination as the fleet grows. One trigger, one mechanical fan-out.
