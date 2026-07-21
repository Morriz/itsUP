---
description: Acceptance scenario for CrowdSec enforcement attachment — when
  crowdsec.enabled is set, the generated Traefik static config attaches the
  crowdsec bouncer middleware at the HTTP entrypoints so every HTTP router
  inherits enforcement, with the router IP and private LAN ranges exempt from
  bans.
delivered_by:
  - crowdsec-enforcement-detached
---

# CrowdSec Enforcement — Spec

## What it is

itsUP wires CrowdSec's detection into Traefik's request path at
artifact-generation time: when `projects/itsup.yml` sets `crowdsec.enabled`,
the generated `proxy/traefik/traefik.yml` attaches the `crowdsec@file` bouncer
middleware to the HTTP entrypoints (`web`, `web-secure`), so every HTTP router
— docker-label and file-provider alike — inherits enforcement without
per-router wiring. The middleware itself is defined in
`proxy/traefik/dynamic/middlewares.yml` (see `project/spec/itsup-config`);
this contract covers its attachment.

The business value is that a CrowdSec ban actually blocks traffic: a banned
client receives a 403 at the proxy instead of reaching an upstream service.
The bouncer exempts the router IP and the private LAN ranges from enforcement
so a misresolved client IP can never mass-ban legitimate internal traffic.
The scenario pins the generated attachment so a regression in the generation
pipeline — enforcement silently detaching from the request path — is caught
before it ships.

### Use cases

The scenario below is bound by exactly one functional test in
`tests/deployment/test_crowdsec_enforcement.py`; the test invokes
`write_traefik_config` and `write_middleware_config` against a temporary
project tree and asserts the generated YAML structure.

#### UC-CSE1: The bouncer middleware is attached at the HTTP entrypoints iff enforcement is enabled

```gherkin
Given projects/itsup.yml declares crowdsec.enabled: true
When the proxy Traefik static config is generated
Then the web and web-secure entrypoints each list crowdsec@file in their HTTP middlewares
And the generated bouncer middleware exempts the router IP and the private LAN ranges from enforcement
And when crowdsec.enabled is false the generated entrypoints list no crowdsec middleware
```

## Canonical fields

- Attachment point: entrypoint-level `http.middlewares` on `web` and
  `web-secure` in the generated `proxy/traefik/traefik.yml`, gated on
  `crowdsec.enabled`. TCP/UDP entrypoints carry no HTTP middleware chain.
- Ban exemption: the bouncer middleware's `clientTrustedIPs` in the generated
  `proxy/traefik/dynamic/middlewares.yml` covers the router IP
  (`get_trusted_ips()`) and the RFC1918 private ranges.

## See Also

- docs/project/design/artifact-generation.md
- docs/project/spec/itsup-config.md
