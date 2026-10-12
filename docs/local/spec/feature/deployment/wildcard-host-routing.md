---
description: Acceptance scenarios for wildcard host routing — a route declared for a
  wildcard host serves every single-label subdomain under it from the route's upstream
  with a publicly trusted certificate obtained by DNS challenge, while single-host
  routes keep their HTTP-challenge certificates.
delivered_by:
  - https-host-upstream
---

# Wildcard Host Routing — Spec

## What it is

An ingress route can be declared for a wildcard host. Every single-label
subdomain under it reaches the route's upstream, served with a publicly trusted
wildcard certificate that the proxy obtains and renews through a DNS challenge at
the zone's DNS provider. The DNS-provider credential is held in itsUP's encrypted
secrets and reaches only the proxy. Single-host routes keep obtaining their
certificates through the HTTP challenge.

The business value is that an unbounded family of hosts — one DNS label per item,
such as live previews — is served by one route and one certificate, with no
per-host declaration and no manual certificate handling.

### Use cases

#### UC-WHR1: Any single-label subdomain of a wildcard route reaches its upstream

```gherkin
Given a route declared for a wildcard host
When a browser requests a single-label subdomain under that host
Then the request is answered by the route's upstream
```

#### UC-WHR2: A wildcard route is served with a publicly trusted certificate obtained by DNS challenge

```gherkin
Given a route declared for a wildcard host whose zone's DNS provider credential is configured
When the proxy serves that route
Then a browser requesting any single-label subdomain under it is presented a publicly trusted certificate valid for that subdomain
And the certificate was obtained through a DNS challenge at the zone's provider
```

#### UC-WHR3: Single-host routes keep their HTTP-challenge certificates

```gherkin
Given a fleet with single-host routes and a wildcard route
When the proxy obtains and renews certificates
Then each single-host route keeps a certificate obtained through the HTTP challenge
```

#### UC-WHR4: The DNS-provider credential never appears in clear text in generated artifacts

```gherkin
Given a DNS-provider credential held in itsUP's encrypted secrets
When the operator or an agent generates the proxy artifacts
Then no generated artifact contains the credential in clear text
```

## Canonical fields

- Declaration: an ingress route's host (`local/projects/itsup/spec/project-config`).
- Certificate resolvers and wildcard matching in generated proxy configuration:
  `local/projects/itsup/design/artifact-generation`.
- Credential storage and loading: `local/projects/itsup/spec/secrets-management`.

## See Also

- docs/local/spec/feature/deployment/pinned-upstream-tls.md
