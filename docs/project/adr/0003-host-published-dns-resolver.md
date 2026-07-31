---
description: 'itsUP publishes the DNS honeypot on the proxynet gateway address so every container reaches one logged resolver from its own network namespace, rejecting per-project DNS edge networks because they multi-home the honeypot across every project bridge and reopen the lateral-movement surface segmentation exists to close.'
date: '2026-07-31'
number: 3
---

# Publish the DNS Honeypot on the Proxynet Gateway — ADR

## Context

itsUP injected `dns: [172.20.0.253, 127.0.0.11]` into every generated upstream
service, while network segmentation grants `proxynet` membership only to services
carrying an ingress row. For the 20 non-ingress services across 9 projects, both
entries are unusable: `172.20.0.253` is off their networks, and `127.0.0.11` names
the container's own embedded resolver as its own upstream. Internal names still
resolved — the embedded resolver answers siblings from the container's own
namespace — so the defect stayed invisible until a service made an external
lookup, which is how it surfaced on ERPNext's SMTP send.

Docker's documentation settles the constraint: *"DNS requests will be forwarded
from the container's network namespace so, for example, `--dns=127.0.0.1` refers
to the container's own loopback address."* Any injected upstream must therefore be
reachable from the asking container's own namespace.

The honeypot is not only a resolver. Per `project/design/container-security-monitor`
it is the monitor's trust oracle: an outbound IP is treated as legitimate only if
some container resolved it through the honeypot, whose query log the monitor
tails. Giving isolated services any resolver that bypasses the honeypot would
leave their legitimate outbound connections without forward-DNS history, and the
monitor reads that absence as hardcoded-IP C2.

So the decision had to satisfy both at once: a resolver reachable from every
container namespace, and one that all DNS still transits.

## Decision

Publish the honeypot on **`172.20.0.1:53`, the proxynet gateway address**, over
both UDP and TCP, and inject that single address as every generated service's
sole resolver. The circular `127.0.0.11` upstream is removed; Docker's embedded
resolver remains each container's resolver and continues answering sibling names
from the container's own namespace.

The address is host-owned, already pinned in `dns/docker-compose.yml` and reserved
in `lib/data.py:PROXYNET_RESERVED_IPS`, and is not routable from the LAN. Firewall
containment restricting the listener to Docker bridge sources is part of the
decision, not an optional hardening step.

`SSH_HOST` (`192.168.1.30`) was the first candidate and is unavailable: AdGuard
already binds it on port 53 for both protocols. The gateway address avoids that
collision and, being non-LAN-routable, exposes strictly less.

## Alternatives considered

**Per-project DNS edge networks with a multi-homed honeypot.** Give each project
a dedicated `project-X--dns` network and attach the honeypot to all of them, so
DNS reachability never depends on proxynet. Rejected: it multi-homes the honeypot
across every project bridge, making one container a member of every project's
network — the concentrated routing surface that network segmentation exists to
prevent, and the concern plan review raised against the earlier draft. It also
multiplies networks linearly with project count, and each new project silently
extends the honeypot's membership.

**Daemon-level `dns` in `daemon.json`.** Rejected on vendor evidence: those
addresses are contacted from the container's namespace like any other upstream,
so the setting inherits the identical reachability constraint and fixes nothing.

**Give isolated services public resolvers.** Rejected: it fixes resolution by
removing the services most likely to make external calls from the monitor's
oracle — trading a documented, code-enforced security control for a one-line
change.

## Consequences

- DNS reachability becomes a property of the host-published listener rather than
  of network membership, so `project/design/artifact-generation` invariant 6 and
  the UC-DNS1 contract change accordingly.
- Oracle coverage now depends on the listener being reachable and contained, not
  on proxynet membership. `project/design/security-architecture` records that
  shift.
- The listener's containment must hold on every path that publishes it, including
  ordinary `itsup apply` reconciliation — not only on runtime install.
- Cross-bridge delivery to a host-owned gateway address is host-local rather than
  bridge-to-bridge, so Docker's isolation chains should not apply. This is the
  one premise the vendor documentation does not settle, and it is gated by a live
  host probe before any mutation.
