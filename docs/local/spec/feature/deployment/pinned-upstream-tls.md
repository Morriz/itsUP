---
description: Acceptance scenarios for pinned upstream TLS — an external-host HTTP route
  re-encrypts its hop to a LAN upstream and forwards only when the upstream presents
  the one certificate the route trusts, validation rejects an enabled route without a
  usable trusted certificate while a disabled one never blocks the fleet, and
  long-lived connections survive the route.
delivered_by:
  - https-host-upstream
---

# Pinned Upstream TLS — Spec

## What it is

An external-host HTTP route can reach a service on another machine over HTTPS,
trusting exactly one certificate that the upstream presents. The container host's
proxy keeps terminating public TLS with the certificates itsUP manages, then
re-encrypts the hop, so nothing on the route crosses the LAN in clear text and
the proxy forwards only to the machine holding that certificate's key. The
trusted certificate is public material declared with the project, not a secret.

The business value is that a service which cannot run as a container on the
container host — such as a native process on another LAN machine — is served
through the one itsUP fleet with its public certificates in one place, and with
an encrypted, authenticated LAN hop that has nothing to renew.

### Use cases

#### UC-PUT1: A pinned route forwards to its upstream over TLS

```gherkin
Given an external-host project whose HTTP route declares an encrypted upstream and its trusted certificate
And the upstream serves TLS with that certificate
When a client requests the route's public host
Then the operator sees the request answered by the upstream
And the hop from the container host to the upstream is TLS-encrypted
```

#### UC-PUT2: An upstream presenting a different certificate is refused

```gherkin
Given an external-host HTTP route declaring an encrypted upstream and its trusted certificate
And the machine answering at the upstream address presents a different certificate
When a client requests the route's public host
Then the request is not forwarded to that machine
And no unverified or plaintext connection to the upstream is attempted
```

#### UC-PUT3: An enabled route without a usable trusted certificate fails validation

```gherkin
Given an enabled project whose encrypted-upstream route names a trusted certificate that is missing or is not a valid certificate
When the operator or an agent validates the configuration
Then validation fails naming the project and the certificate problem
And no deploy proceeds
```

#### UC-PUT4: A disabled project awaiting its certificate never blocks the fleet

```gherkin
Given a disabled project whose encrypted-upstream route has no trusted certificate present yet
When the operator or an agent validates the configuration
Then that project raises no validation error
And every other project validates and deploys as before
```

#### UC-PUT5: Long-lived connections stay open through a pinned route

```gherkin
Given a browser holding a WebSocket to an upstream through a pinned route
When the connection stays open with long idle stretches between messages
Then the proxy does not close the connection on a timeout
And it stays open for as long as the browser and the upstream keep it open
```

## Canonical fields

- Declaration: an external-host project's ingress route
  (`local/projects/itsup/spec/project-config`).
- Generation of the upstream transport and the proxy's access to the trusted
  certificate: `local/projects/itsup/design/artifact-generation`.
- Fleet-wide HTTPS controls (security headers, rate limit, CrowdSec) apply to
  these routes unchanged:
  `local/projects/itsup/spec/feature/deployment/http-security-middlewares`,
  `local/projects/itsup/spec/feature/deployment/crowdsec-enforcement`.

## See Also

- docs/local/spec/feature/deployment/wildcard-host-routing.md
- docs/local/spec/feature/deployment/config-validation.md
