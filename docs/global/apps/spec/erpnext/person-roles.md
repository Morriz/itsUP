---
description: Mapping from a person's company role to the ERPNext roles they are granted on that company's site.
---

# ERPNext Person Roles — Spec

## Required reads

- @~/.teleclaude/docs/erp/procedure/person-onboarding.md

## What it is

Two independent authority axes decide what a human gets on an ERPNext site, and neither
derives from the other:

- **Platform role** — the person's role in the operating platform (`admin`, `member`,
  `contributor`, `newcomer`). It governs authority over the platform itself and decides who
  may change a company's roster. It grants nothing inside a business.
- **Company role** — the person's relationship to one business. It is stated per company
  and is the only input to ERPNext provisioning.

A platform admin with no relationship to a company receives nothing on that company's site;
a contributor who runs a company's books receives that company's grants. Deriving business
authority from platform authority reads one domain's identity as another's, and is a defect.

## Canonical fields

Company role to ERPNext grants, applied on the company's own site:

- **`owner`** — the business principal. Granted `System Manager` plus the Manager role and
  its User counterpart for each business surface in use (Accounts, Sales, Purchase, Stock,
  Projects). `System Manager` is bounded here because tenancy is structural: one site per
  tenant means the grant reaches that company's own records and no other tenant's.
- **`member`** — a day-to-day operator. Granted the User-level role for each surface the
  person works, and a Manager role only where that person genuinely administers the surface.
  Never granted `System Manager`.
- **absent from the company's roster** — no ERPNext user exists for that person on that
  site. This is the default for everyone whose company role is unstated.

## Known caveats

- ERPNext roles are additive, not hierarchical: a Manager role does not imply its User role,
  and item master maintenance requires `Item Manager` regardless of Stock roles. Grant each
  role the person needs explicitly.
- Passwords are never handed to a person. Provisioning triggers ERPNext's native welcome
  email so the person sets their own credentials, which requires the site's outgoing email
  account to be configured first; without it the invitation never leaves the site.
- The `Administrator` account is not a person's login. Its password is a site bootstrap
  secret and stays in the deployment's secret store.
- A company's agent operator identity is not a person and holds no company role; it is
  established by company onboarding.
- Company rosters are not yet part of company configuration. Until they are, an agent
  confirms a person's company role with that company's owner before provisioning, and
  records the granted roles with the person's onboarding evidence.
