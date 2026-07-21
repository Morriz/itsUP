---
description: Acceptance scenario for the default HTTP security middlewares — the generated
  Traefik static config attaches default-headers and rate-limit at the web-secure
  entrypoint so every HTTPS router inherits security headers and rate limiting.
---

# HTTP Security Middlewares — Spec

## What it is

itsUP applies its baseline HTTP hardening at artifact-generation time: the
generated `proxy/traefik/traefik.yml` attaches the `default-headers@file` and
`rate-limit@file` middlewares to the `web-secure` entrypoint, so every HTTPS
router — docker-label and file-provider alike — inherits security headers
(HSTS, `X-Content-Type-Options`, `X-Frame-Options`, XSS filter) and per-client
rate limiting without per-router wiring. The middlewares themselves are defined
in `proxy/traefik/dynamic/middlewares.yml` and tunable through the
`projects/middlewares.yml` override surface (see `project/spec/itsup-config`);
this contract covers their attachment.

The business value is that the hardening actually reaches responses: an HTTPS
response served through the proxy carries the security headers, and a single
client cannot flood an upstream service past the configured rate. The scenario
pins the generated attachment so a regression in the generation pipeline — the
hardening silently detaching from the request path — is caught before it
ships.

### Use cases

The scenario below is bound by exactly one functional test in
`tests/deployment/test_http_security_middlewares.py`; the test invokes
`write_traefik_config` and `write_middleware_config` against a temporary
project tree and asserts the generated YAML structure.

#### UC-HSM1: The default security middlewares are attached at the HTTPS entrypoint

```gherkin
Given a valid itsUP infrastructure configuration
When the proxy Traefik static config is generated
Then the web-secure entrypoint lists default-headers@file and rate-limit@file in its HTTP middlewares
And the generated dynamic middlewares define both default-headers and rate-limit
```

## Canonical fields

- Attachment point: entrypoint-level `http.middlewares` on `web-secure` in the
  generated `proxy/traefik/traefik.yml`, unconditional — both middlewares are
  always defined, so the attachment carries no config gate. The `web`
  entrypoint carries neither (it serves HTTP→HTTPS redirects and the ACME
  HTTP-01 path). TCP/UDP entrypoints carry no HTTP middleware chain.
- Chain order on `web-secure`: `default-headers@file`, `rate-limit@file`,
  then any conditionally attached enforcement middleware (see
  `project/spec/feature/deployment/crowdsec-enforcement`).
- Rate-limit values are defined in the dynamic middlewares file and tunable
  via the `projects/middlewares.yml` override; the attachment contract does
  not pin them.

## See Also

- docs/project/design/artifact-generation.md
- docs/project/spec/feature/deployment/crowdsec-enforcement.md
- docs/project/spec/itsup-config.md
