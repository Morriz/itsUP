---
description: Verified Docker container DNS semantics for the itsUP resolver-injection contract — the embedded resolver at 127.0.0.11, the rule that upstream DNS is contacted from the container's own network namespace (making an off-network or self-referential upstream unresolvable by construction), and why daemon-level dns inherits the same constraint.
---

# Docker — Container DNS Resolution

## What it is

Containers attached to a user-defined network resolve names through Docker's
**embedded DNS server at `127.0.0.11`**, reachable inside each container's own
network namespace. It answers container, service, and network-alias names
directly, and forwards anything it cannot answer to upstream resolvers.

The `dns:` key on a Compose service (equivalently `--dns`) does **not** replace
the embedded resolver. It sets the **upstream forwarders** the embedded resolver
consults for names it cannot answer itself.

## The constraint that governs itsUP's injection

From Docker's networking documentation:

> The embedded DNS server forwards external DNS lookups to the DNS servers
> configured on the host.

> DNS requests will be forwarded from the container's network namespace so, for
> example, `--dns=127.0.0.1` refers to the container's own loopback address.

Two consequences bind itsUP's generated `dns:` lists:

1. **An injected upstream must be reachable from the asking container's own
   namespace.** An address that lives only on a network the container never
   joined is unreachable, and the forward times out. Membership of the network
   the resolver sits on — not merely the resolver existing — is what makes it
   usable.
2. **`127.0.0.11` must never appear as an upstream.** Inside the container it is
   the embedded resolver's own address, so listing it as a forwarder points the
   resolver at itself. It is self-referential, not a fallback.

Internal name resolution is unaffected by either problem: the embedded resolver
answers sibling names from the container's own namespace without consulting any
forwarder. This is why a broken upstream list is invisible to services that only
ever resolve siblings and surfaces only on the first external lookup.

On user-defined networks the embedded resolver "queries upstream servers in
order and stops after a successful response or an `NXDOMAIN` response."

## Daemon-level configuration inherits the same constraint

`dockerd --dns` and the `dns` key in `daemon.json` set the **default** forwarder
list for containers. They do not change where forwarding originates: those
addresses are still contacted from the container's network namespace. A daemon
default therefore cannot make an otherwise-unreachable resolver reachable.

## Contrast: default bridge vs user-defined networks

Containers on the **default** bridge receive a copy of the host's
`/etc/resolv.conf`. Containers on **user-defined** networks use the embedded
resolver described above. itsUP's generated projects are all user-defined
networks, so the embedded-resolver semantics are the ones that apply.

## Comparable production pattern

Publishing a resolver on a host-owned address and pointing containers at it —
rather than joining every container to the resolver's network — is the
established shape for host-level DNS filtering and logging deployments
(Pi-hole and AdGuard Home both document binding the resolver to a specific host
address and configuring clients, including containers, to use it). itsUP's own
`adguard` project already runs this pattern against the host LAN address, which
is the in-repo reference implementation for the binding shape.

## Source

Docker official documentation, `docs.docker.com/engine/network/` (DNS services
for containers) and `docs.docker.com/reference/cli/dockerd/` (`--dns`,
`--dns-search`, `--dns-opt`). Retrieved 2026-07-31.
