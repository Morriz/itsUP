---
description: Add a tenant site to the itsUP-operated ERPNext bench — desired-state edit, admin secret, reconcile, verify.
---

# Create An ERPNext Site — Procedure

## Goal

A new Frappe site exists on the ERPNext bench, answers at its FQDN, and its administrator
bootstrap password is stored in itsUP secrets. Tenancy is site-per-tenant: each tenant gets
its own site with its own database on the bench's shared MariaDB service
(`erp/concept/multi-tenancy`).

## Preconditions

- The `itsup` CLI is installed and on PATH, with access to the `projects/` and `secrets/`
  repos.
- The site FQDN is chosen and routable to the fleet (e.g. `<tenant>.erpnext.instrukt.ai`).
- An explicit human or procedure-level request names the tenant; site creation allocates a
  database and is not a casual operation.

## Steps

Follow the itsUP GitOps workflow (`infra/procedure/itsup-gitops-workflow`) with this
project-specific shape:

1. **`itsup pull`**, then locate the project files with `itsup list-project-files erpnext`.
2. **Extend site creation in the compose file.** The `erpnext-create-site` service runs a
   guarded, idempotent `bench new-site --install-app erpnext "$SITE_NAME"` (it skips a site
   whose directory already exists) followed by `bench --site "$SITE_NAME" set-config
   host_name "https://$SITE_NAME"`. Add the new site by extending that command with a second
   guarded `bench new-site` + `set-config` block for the new FQDN, using a dedicated
   admin-password variable (e.g. `ADMIN_PASSWORD_<TENANT>`) rather than reusing another
   site's secret. The frontend needs no per-site change: it resolves sites from the Host
   header (`FRAPPE_SITE_NAME_HEADER=$$host`).
3. **Add the ingress entry** in `itsup-project.yml`: route the new FQDN to the
   `erpnext-frontend` service on port 8080.
4. **Add the admin bootstrap password to the project's secrets**: `itsup decrypt <name>`,
   add the new variable, `itsup encrypt <name> --delete`. The password never lands in
   compose files, argv, chat, or logs.
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

Which sites exist is itsUP desired state and nothing else's — no other repo or registry
keeps a site list. One admin-password secret per site, never shared across tenants. Site
creation is complete only when the FQDN verifiably answers; handing an unverified site to
business onboarding wastes the next agent's session on infra diagnosis.

## See Also

- ~/.teleclaude/docs/infra/procedure/itsup-gitops-workflow.md
- ~/.teleclaude/docs/apps/procedure/erpnext/delete-site.md
