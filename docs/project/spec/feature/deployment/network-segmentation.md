---
description: Acceptance scenarios for itsUP's generation-time network segmentation
  — the three network states, ingress-gated proxynet membership, per-edge least-privilege
  egress, provider-side edge creation, DNS honeypot injection, and static-IP pinning
  as rendered into the generated upstream docker-compose.yml.
---

# Network Segmentation — Spec

## Required reads

@docs/project/design/network-segmentation.md

## What it is

itsUP assigns Docker networks to each upstream service at artifact-generation
time, so that a compromised container reaches only the services its project
explicitly declared. The contract is realized by
`bin/write_artifacts.py:write_upstream()`, which writes the per-service
`networks:` blocks and the top-level `networks:` map into
`upstream/{project}/docker-compose.yml`; the design and its invariants live in
`project/design/network-segmentation`.

The business value is a default-deny posture between projects: cross-project or
external reachability is granted only where an `ingress` or `egress` declaration
earns it, and each grant is scoped to the single provider service named — not the
provider's other services and not other consumers of that service. These
scenarios pin that observable output so a regression in the generated compose
network topology is caught before it ships.

### Use cases

The scenarios below capture the three network states (project-local isolation,
ingress-gated proxynet membership, per-edge egress) plus DNS injection and
static-IP pinning. Each is bound by exactly one functional test in
`tests/deployment/test_network_segmentation.py`; the test mocks only the
`load_project` filesystem line, invokes `write_upstream`, and asserts the
generated compose structure via the imported `edge_network_name` helper.

#### UC-PROX1: A service with an ingress row joins proxynet; one without does not

```gherkin
Given a project whose compose declares two services
And only the first service carries an ingress row with a domain
When the upstream compose is generated
Then the first service's networks include proxynet
And the second service's networks do not include proxynet
```

#### UC-ISO1: A service with neither ingress nor egress stays project-local only

```gherkin
Given a project whose compose declares a service
And that service carries neither an ingress row nor an egress declaration
When the upstream compose is generated
Then the service's networks do not include proxynet
And the service's networks include no per-edge egress network
```

#### UC-DNS1: Every service receives the DNS honeypot and Docker DNS

```gherkin
Given a project whose compose declares services with no explicit dns
When the upstream compose is generated
Then every service's dns list is the honeypot address followed by the Docker DNS address
```

#### UC-DNS2: An explicit dns list on an ingress row replaces the honeypot injection

```gherkin
Given a project whose service carries an ingress row with an explicit dns list
When the upstream compose is generated
Then that service's dns list equals the declared list verbatim
And the honeypot address is not injected
```

#### UC-EGR1: A consumer's egress joins a per-edge network, never the provider's default

```gherkin
Given a project whose service declares egress to a single provider service
When the upstream compose is generated
Then the service joins the per-edge network for that consumer, provider, and service
And that per-edge network is declared external at the top level
And the provider's shared default network is not declared
```

#### UC-EGR2: Multiple egress entries produce separate per-service edge networks

```gherkin
Given a project whose service declares egress to two services of the same provider
When the upstream compose is generated
Then the service joins a distinct per-edge network for each provider service
And the provider's shared default network is not declared
```

#### UC-EGR3: A service with both ingress and egress joins proxynet and its edge network

```gherkin
Given a project whose service carries both an ingress row and an egress declaration
When the upstream compose is generated
Then the service's networks include proxynet
And the service's networks include the per-edge egress network
And the provider's shared default network is not declared
```

#### UC-PROV1: The provider creates the named edge network and attaches only the declared service

```gherkin
Given a provider project whose compose declares two services
And one consumer has declared egress to the first of those services
When the provider's upstream compose is generated with that reverse-egress mapping
Then the per-edge network is declared at the top level with an explicit Docker name
And only the declared service is attached to that per-edge network
And the other provider service is not attached to it
```

#### UC-PROV2: A provider service on an edge network retains its default network

```gherkin
Given a provider project whose compose declares two services
And one consumer has declared egress to the first of those services
When the provider's upstream compose is generated with that reverse-egress mapping
Then the declared service's networks include both the per-edge network and the default network
And the other provider service is not attached to the per-edge network
```

#### UC-PROV3: Two consumers of the same service get separate, disjoint edge networks

```gherkin
Given a provider project whose compose declares a service
And two distinct consumers have each declared egress to that service
When the provider's upstream compose is generated with that reverse-egress mapping
Then the two per-edge network names differ
And both per-edge networks are declared at the top level with explicit Docker names
```

#### UC-IP1: An ingress static IP renders the networks block in mapping form on proxynet

```gherkin
Given a project whose service carries an ingress row with a static ipv4_address
When the upstream compose is generated
Then that service's networks block is rendered in mapping form
And the proxynet entry pins the declared ipv4_address
```

#### UC-IP2: Without a static IP the networks block stays in list form

```gherkin
Given a project whose service carries an ingress row with no ipv4_address
When the upstream compose is generated
Then that service's networks block is rendered in list form
And it includes proxynet
```

## Canonical fields

The scenarios exercise the generation-time contract of
`bin/write_artifacts.py:write_upstream(project_name, reverse_graph)`:

- **Inputs (mocked via `load_project`)** — a compose `dict` of service
  definitions plus a `TraefikConfig` carrying `ingress` rows (`Ingress`) and
  `egress` `project:service` strings. On the provider side, the `reverse_graph`
  argument maps this project to its `(consumer, service)` pairs.
- **Output** — the generated `upstream/{project}/docker-compose.yml`: each
  service's `networks:` block (list form, or mapping form when a static IP is
  pinned), each service's injected `dns:` list, and the top-level `networks:` map
  (consumer edge networks declared `external: true`; provider edge networks
  declared with an explicit `name:`).
- **Edge-network identity** — asserted through the imported
  `lib/data.py:edge_network_name(consumer, provider, service)` helper, never a
  hand-built string literal.
