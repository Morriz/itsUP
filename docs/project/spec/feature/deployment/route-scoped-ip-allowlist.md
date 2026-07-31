---
delivered_by: [gated-file-endpoint]
description: Acceptance scenarios for the route-scoped source-IP allowlist — an ingress row carrying allow_source_ips generates a per-route Traefik ipAllowList middleware attached only to that router, and external-host routers are disambiguated by a per-route ingress-loop index suffix so multiple routes can share one host:port.
---

# Route-Scoped Source-IP Allowlist — Spec

## What it is

itsUP expresses a per-route origin gate at artifact-generation time. An
`Ingress` row carrying `allow_source_ips` (a list of IPs/CIDRs) makes the
generator emit a Traefik v3 `ipAllowList` middleware whose `sourceRange` is that
list, and attach it to that route's dynamic-file HTTP router alone — leaving
every other router, and the shared `web-secure` entrypoint chain, untouched. A
route without the field emits no per-route middleware.

Because each external-host route now gets a per-route-unique router identity —
`{project}-{host}-{port}` plus the route's ingress-loop index — two ingress rows
sharing one external `host:port` (for example an unauthenticated `/redirect` and
an origin-gated `/file` on the same API host) generate two distinct routers
instead of colliding on one router key. The identity is unique by construction
(not derived from the path), so it cannot collide.

The business value is that a single route can be restricted to a fixed origin
without a bespoke firewall and without affecting neighbouring routes: the gate
rides the generated proxy config, so a regression that detaches the gate or
collapses the two routes is caught before it ships. The origin value itself is
evaluated by Traefik against the request's remote address, which under itsUP's
trusted PROXY protocol from `routerIP` is the conveyed client IP.

### Use cases

The scenarios below are bound by functional tests in
`tests/deployment/test_route_scoped_ip_allowlist.py`, which invoke the real
`write_dynamic_routers` generation surface against a temporary external-host
project tree and assert the generated `routers-http.yml` structure, plus two
model-validation tests.

#### UC-RSIP1: Two routes on one external host:port render as distinct routers

```gherkin
Given an external-host project with two ingress rows sharing one host and port
When the dynamic Traefik routers are generated
Then the generated routers-http.yml contains two distinct routers with distinct identities
And each router references its own matching service
```

#### UC-RSIP2: A route declaring allow_source_ips gets an ipAllowList middleware attached to only that router

```gherkin
Given an ingress row that declares allow_source_ips with one or more IPs or CIDRs
When the dynamic Traefik routers are generated
Then that route's router lists a per-route ipAllowList middleware in its middlewares
And the generated ipAllowList middleware's sourceRange equals the declared allow_source_ips
```

#### UC-RSIP3: A malformed allow_source_ips entry is rejected, naming the entry

```gherkin
Given an ingress row whose allow_source_ips contains a value that is not a valid IP or CIDR
When the project configuration is loaded and validated
Then validation fails naming the malformed entry
```

#### UC-RSIP4: A route without allow_source_ips carries no per-route ipAllowList

```gherkin
Given an ingress row that does not declare allow_source_ips
When the dynamic Traefik routers are generated
Then that route's router carries no ipAllowList middleware
```

#### UC-RSIP5: A present-but-empty allow_source_ips is rejected as an empty allowlist

```gherkin
Given an ingress row whose allow_source_ips is present but an empty list
When the project configuration is loaded and validated
Then validation fails with an empty-allowlist error
```

## Canonical fields

- Trigger: an `Ingress` row with a non-empty `allow_source_ips`
  (`project/spec/project-config`).
- Attachment point: per-route `middlewares` on the route's file-provider HTTP
  router in `proxy/traefik/dynamic/routers-http.yml`, plus the
  `http.middlewares.<router-name>-ipallowlist.ipAllowList.sourceRange` definition
  in the same file. Distinct from the entrypoint-level chain
  (`project/spec/feature/deployment/http-security-middlewares`), which stays
  global and unchanged.
- Router identity: each external-host route gets a per-route-unique
  (collision-free) router/service identity — `{project}-{host}-{port}` plus the
  route's index within that host's ingress list — so two routes on one
  `host:port` (e.g. an open `/redirect` and a gated `/file`) render as distinct
  routers instead of one overwriting the other. The suffix is unique by
  construction, so no separate uniqueness validation is needed.
- IP strategy: none set — Traefik matches `sourceRange` against the request's
  remote address, which is the PROXY-protocol-conveyed client IP under the
  `routerIP` trust configured on every entrypoint.

## See Also

- docs/project/design/artifact-generation.md
- docs/project/spec/project-config.md
- docs/project/spec/feature/deployment/http-security-middlewares.md
- docs/project/spec/feature/api/gated-file-serving.md
