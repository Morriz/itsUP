---
description: Verified Traefik v3 IPAllowList HTTP middleware semantics for the itsUP per-route origin gate — sourceRange (CIDR) file-provider config, the default remote-address match strategy, and how it composes with itsUP's PROXY-protocol client-address trust.
---

# Traefik v3 — IPAllowList HTTP Middleware

## What it is

Traefik v3's `ipAllowList` HTTP middleware accepts a request only when the
evaluated client IP falls inside a configured allow list, and rejects it
otherwise (HTTP 403). itsUP uses it to express a **per-route** origin gate: the
middleware is defined and attached to a single dynamic-file router (see
`project/spec/feature/deployment/route-scoped-ip-allowlist`), not at the shared
entrypoint.

## Configuration (file provider, YAML)

```yaml
http:
  middlewares:
    <name>-ipallowlist:
      ipAllowList:
        sourceRange:
          - "203.0.113.7/32"
          - "198.51.100.0/24"
  routers:
    <name>:
      middlewares:
        - <name>-ipallowlist
```

- `sourceRange` — the allowed IPs/CIDRs (CIDR notation). This is the only
  required field. An empty/absent `sourceRange` is a misconfiguration.
- The middleware name is referenced from the router's `middlewares` list; with
  the file provider the reference is the bare middleware key (same file) or
  `<name>@file` across files.

## Client-IP evaluation strategy

- With **no `ipStrategy`** set, `ipAllowList` matches `sourceRange` against the
  request's **remote address** — the address of the connection Traefik sees.
- `ipStrategy.depth` / `ipStrategy.excludedIPs` exist for selecting a client IP
  out of an `X-Forwarded-For` chain when Traefik sits behind another forwarding
  proxy. They are **not** needed when the true client address arrives as the
  connection's remote address.

### Interaction with itsUP's trust configuration

itsUP terminates ingress at Traefik and configures, on every entrypoint,
`proxyProtocol.trustedIPs` and `forwardedHeaders.trustedIPs` to the trust list
built by `get_trusted_ips()` (the `routerIP` from `projects/itsup.yml`) — see
`tpl/traefik.yml.j2`. When the upstream hop at `routerIP` speaks PROXY protocol
to Traefik, Traefik's remote address for the request is the PROXY-protocol
conveyed client IP. Therefore the **default (remote-address) `ipAllowList`
strategy is correct for itsUP** and no `ipStrategy` is required; the gate is only
as accurate as the client address PROXY protocol conveys, which is why the
capability depends on correct client-IP trust (`client-ip-trust-fix`).

## Sources

- https://doc.traefik.io/traefik/reference/routing-configuration/http/middlewares/ipallowlist/ (official IPAllowList reference)
- https://doc.traefik.io/traefik/v3.5/middlewares/http/ipallowlist/ (v3.5 IPAllowList middleware)
