---
description: Remove a tenant site from the ERPNext bench — human-gated destructive runbook with backup, desired-state cleanup, and host-side drop.
---

# Delete An ERPNext Site — Procedure

## Goal

A tenant site and its database are removed from the ERPNext bench deliberately: ratified by
a human, backed up first, cleaned out of desired state so reconciliation cannot recreate it,
and dropped on the host.

## Preconditions

- An explicit human decision names the site for deletion. This drops a tenant's database;
  no automation, onboarding, or offboarding flow triggers it implicitly.
- A verified backup of the site exists off-host, or the human has explicitly waived it.

## Steps

1. **Back up first.** On the container host, run `bench --site <fqdn> backup
   --with-files` inside the bench container and move the artifacts off-host. Verify the
   files exist and are non-empty before proceeding.
2. **Remove the site from desired state** via the itsUP GitOps workflow
   (`infra/procedure/itsup-gitops-workflow`): delete the site's guarded block from the
   `erpnext-create-site` command and its ingress entry from `itsup-project.yml`, then
   `itsup validate` and `itsup commit`. Doing this first prevents the reconciler from
   recreating the site after the drop.
3. **Drop the site on the host.** Inside the bench container: `bench drop-site <fqdn>
   --db-root-password <root>` (root credentials come from the project's secrets). This
   removes the site's database and site directory.
4. **Remove the site's admin-password secret** from the project's secrets
   (`itsup decrypt <name>`, delete the variable, `itsup encrypt <name> --delete`).
5. **Verify** the FQDN no longer serves the site and the bench's site list no longer
   contains it.

## Outputs

- The site is absent from itsUP desired state, the bench, and the secrets file.
- A verified off-host backup exists (unless explicitly waived).

## Recovery

- **Deletion was a mistake:** recreate the site (`apps/procedure/erpnext/create-site`) and
  restore the backup inside the bench container with `bench --site <fqdn> restore`.
- **The reconciler recreated the site:** step 2 was skipped or not committed — remove the
  desired-state entries and re-apply before dropping again.

## Discipline

This is the single most destructive operation in the fleet's ERP surface: it erases a
tenant's system of record. The human gate and the backup are not ceremony — never fold this
procedure into an automated flow, never run it on a hunch about a "stale" site, and never
skip the desired-state cleanup that keeps the drop from silently reverting.

## See Also

- ~/.teleclaude/docs/infra/procedure/itsup-gitops-workflow.md
- ~/.teleclaude/docs/apps/procedure/erpnext/create-site.md
