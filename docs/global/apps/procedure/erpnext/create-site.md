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
  needs no separate action. TLS uses one exact-domain certificate whose SAN list contains
  every configured site; the HTTP-01 resolver does not issue wildcard certificates.
- An explicit human or procedure-level request names the tenant; site creation allocates a
  database and is not a casual operation.

## Steps

Follow the itsUP GitOps workflow (`infra/procedure/itsup-gitops-workflow`) with this
project-specific shape:

1. **`itsup pull`**, then locate the ERPNext desired-state files with
   `itsup projects erpnext`.
2. **Add the site to the provisioning file.** Append its FQDN and dedicated
   admin-password variable name to `sites.json`, then expose that variable to the existing
   `erpnext-create-sites` service. The single service reads every entry and runs guarded,
   idempotent `bench new-site --install-app erpnext "$SITE_NAME"` for sites whose directory
   does not exist, then sets each site's `host_name` to its HTTPS FQDN.
3. **Add the FQDN to the ingress certificate.** The ERPNext project has one HTTP ingress
   row for `erpnext-frontend`. Keep its first site as `tls.main` and add every other site
   under `tls.sans`. itsUP renders one router with a combined exact-domain Host rule, one
   backend service, and one certificate covering those names. The frontend resolves the
   selected site from the Host header (`FRAPPE_SITE_NAME_HEADER=$$host`).
4. **Add the admin bootstrap password to the ERPNext secret set**: `itsup decrypt erpnext`,
   add the site-specific variable, `itsup encrypt erpnext --delete`. Desired-state files
   contain only the variable reference; the password value never lands in chat or logs.
5. **`itsup validate`, then `itsup commit`.** The container host reconciles;
   `erpnext-create-sites` re-runs idempotently and creates only missing sites.
6. **Verify** the site answers at its FQDN (`/api/method/ping` and the login page) before
   handing it to any operating procedure.

## Outputs

- The site exists in itsUP desired state and on the reconciled bench, with its own database.
- The site's admin bootstrap password lives in itsUP secrets under a site-specific variable.
- The FQDN is routed and verified.

## Recovery

- **Reconciliation did not create the site:** follow the itsUP GitOps workflow's recovery
  guidance (inspect pipeline and host evidence first); the create-sites container's logs name
  the failing `bench new-site` step.
- **The FQDN is refused with an unrecognized-name TLS error:** the served certificate
  predates the new hostname and the proxy holds it as valid. Invalidate that certificate so
  the proxy requests one covering every name the ingress lists, then retry.
- **The FQDN routes but ERPNext serves the wrong site:** the Host header does not match a
  site directory name — confirm the ingress domain and the site name are identical strings.
- **A re-apply reports the site as existing:** that is the idempotent guard working, not an
  error.

## Discipline

Which sites exist is itsUP desired state and nothing else's. One provisioning service applies
the declared site file; do not create a service or ingress row per tenant. One admin-password
secret per site is never shared across tenants. Site creation is complete only when the FQDN
verifiably answers; handing an unverified site to business onboarding wastes the next agent's
session on infra diagnosis.

## See Also

- ~/.teleclaude/docs/infra/procedure/itsup-gitops-workflow.md
- ~/.teleclaude/docs/apps/procedure/erpnext/delete-site.md
