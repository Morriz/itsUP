---
description: Remove a tenant site from the ERPNext bench — human-gated destructive runbook with desired-state cleanup and host-side drop.
---

# Delete An ERPNext Site — Procedure

## Required reads

- @~/.teleclaude/docs/infra/procedure/itsup-gitops-workflow.md

## Goal

A tenant site and its database are removed from the ERPNext bench deliberately: ratified by
a human, cleaned out of desired state so reconciliation cannot recreate it, and dropped on
the host.

## Preconditions

- An explicit human decision names the site for deletion. This drops a tenant's database;
  no automation, onboarding, or offboarding flow triggers it implicitly.

## Steps

1. **Remove the site from desired state** via the itsUP GitOps workflow
   (`infra/procedure/itsup-gitops-workflow`): remove the site's create service, remove it
   from the `erpnext-sites-ready` dependency list, remove its ingress entry, and remove its
   dedicated admin-password variable from the ERPNext secret set. Then run `itsup validate`
   and `itsup commit`. Doing this first prevents the reconciler from recreating the site
   after the drop.
2. **Drop the site on the host.** Inside the bench container: `bench drop-site <fqdn>
   --db-root-password <root>` (root credentials come from the ERPNext secret set). This
   removes the site's database and site directory.
3. **Verify** the FQDN no longer serves the site and the bench's site list no longer
   contains it.

## Outputs

- The site is absent from itsUP desired state, the bench, and the secrets file.

## Recovery

- **Deletion was a mistake:** recreate the empty site
  (`apps/procedure/erpnext/create-site`); restoring prior tenant data is outside this
  procedure.
- **The reconciler recreated the site:** step 1 was skipped or not committed — remove the
  desired-state entries and re-apply before dropping again.

## Discipline

This is the single most destructive operation in the fleet's ERP surface: it erases a
tenant's system of record. The human gate is not ceremony — never fold this procedure into
an automated flow, never run it on a hunch about a "stale" site, and never skip the
desired-state cleanup that keeps the drop from silently reverting.

## See Also

- ~/.teleclaude/docs/infra/procedure/itsup-gitops-workflow.md
- ~/.teleclaude/docs/apps/procedure/erpnext/create-site.md
