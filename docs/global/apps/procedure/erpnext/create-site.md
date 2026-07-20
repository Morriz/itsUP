---
description: Add a tenant site to the itsUP-operated ERPNext bench — desired-state edit, admin secret, reconcile, verify.
---

# Create An ERPNext Site — Procedure

## Required reads

- @~/.teleclaude/docs/infra/procedure/itsup-gitops-workflow.md

## Goal

A new Frappe site exists on the ERPNext bench, answers at its FQDN, and its administrator
bootstrap password is stored in itsUP secrets. Tenancy is site-per-tenant: each tenant gets
its own site with its own database on the bench's shared MariaDB service
(`erp/concept/multi-tenancy`).

## Preconditions

- The `itsup` CLI is installed and on PATH, with access to the ERPNext desired state and
  encrypted secrets.
- The site FQDN is chosen under a zone the fleet already serves — DNS for
  `*.erpnext.instrukt.ai` resolves to the fleet via a wildcard A record, so per-site DNS
  needs no separate action; routing still requires the per-site ingress entry below.
- An explicit human or procedure-level request names the tenant; site creation allocates a
  database and is not a casual operation.

## Steps

Follow the itsUP GitOps workflow (`infra/procedure/itsup-gitops-workflow`) with this
project-specific shape:

1. **`itsup pull`**, then locate the ERPNext desired-state files with
   `itsup projects erpnext`.
2. **Add one site entry to the compose file.** Each site is a service entry based on the
   shared create-site template. Set its `SITE_NAME` to the full FQDN and bind
   `ADMIN_PASSWORD` to a secret variable used only by that site. Add the service to the
   `erpnext-sites-ready` dependency list. The shared template runs guarded, idempotent
   `bench new-site --install-app erpnext "$SITE_NAME"` and skips a site whose directory
   already exists, then sets `host_name` to its HTTPS FQDN. Do not extend or duplicate the
   shared command. The frontend needs no per-site change: it resolves sites from the Host
   header (`FRAPPE_SITE_NAME_HEADER=$$host`).
3. **Add the ingress entry** in `itsup-project.yml`: route the new FQDN to the
   `erpnext-frontend` service on port 8080.
4. **Add the admin bootstrap password to the ERPNext secret set**: `itsup decrypt erpnext`,
   add the site-specific variable, `itsup encrypt erpnext --delete`. The password never
   lands in compose files, argv, chat, or logs.
5. **`itsup validate`, then `itsup commit`.** The container host reconciles; the create-site
   step re-runs idempotently and creates only the new site.
6. **Verify** the site answers at its FQDN (`/api/method/ping` and the login page) before
   handing it to any operating procedure.

## Outputs

- The site exists in itsUP desired state and on the reconciled bench, with its own database.
- The site's admin bootstrap password lives in itsUP secrets under a site-specific variable.
- The FQDN is routed and verified.

## Recovery

- **Reconciliation did not create the site:** follow the itsUP GitOps workflow's recovery
  guidance (inspect pipeline and host evidence first); the create-site container's logs name
  the failing `bench new-site` step.
- **The FQDN routes but ERPNext serves the wrong site:** the Host header does not match a
  site directory name — confirm the ingress domain and the site name are identical strings.
- **A re-apply reports the site as existing:** that is the idempotent guard working, not an
  error.

## Discipline

Which sites exist is itsUP desired state and nothing else's — no parallel source keeps a
site list. One admin-password secret per site, never shared across tenants. Site creation is
complete only when the FQDN verifiably answers; handing an unverified site to business
onboarding wastes the next agent's session on infra diagnosis.

## See Also

- ~/.teleclaude/docs/infra/procedure/itsup-gitops-workflow.md
- ~/.teleclaude/docs/apps/procedure/erpnext/delete-site.md
