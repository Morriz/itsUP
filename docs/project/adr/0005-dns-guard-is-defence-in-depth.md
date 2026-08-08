---
description: 'itsUP classifies the DNS listener firewall guard as defence-in-depth rather than a mandatory invariant, so a host that cannot establish containment publishes the resolver with a warning and an unrepairable loss alerts instead of withdrawing DNS, because the guarded address is not LAN-routable and a fleet-wide resolution outage costs more than the narrow residue the guard covers.'
date: '2026-08-08'
number: 5
---

# The DNS Listener Guard Is Defence-in-Depth — ADR

## Context

The DNS honeypot is published on `172.20.0.1:53`, the proxynet gateway address,
so that every container reaches one logged resolver from its own network
namespace. A published port is reachable by anything that can route to it, so an
iptables guard restricts the listener to discovered Docker bridge sources.

The earlier record classified that guard as part of the decision rather than
optional hardening. Read as a mandatory invariant, the classification determines
what happens when containment cannot be established, and two behaviours followed
from it: a host unable to install the rules refuses to publish at all, and a host
that loses the rules on an already-running listener stops the DNS stack. Because
the guard is iptables-based, the refusal also made the whole resolver
Linux-only — a macOS container host would decline to publish rather than serve
unguarded.

Those consequences were derived from the classification, never from a stated
threat model. The same record establishes that `172.20.0.1` is a host-owned
gateway address that is **not routable from the LAN**, and every container is
intended to reach it — that reachability is the mechanism being delivered. What
the guard excludes beyond what the address already excludes is host-local
processes and clients routed in over a VPN interface. That residue was never
weighed against the cost of the behaviours the classification produced.

The cost is asymmetric and large. Refusing to publish, or withdrawing a published
listener, denies DNS to every container on the host. The condition being treated
is a narrow exposure on an address the LAN cannot reach; the treatment is a
fleet-wide outage of the resolution path itself.

## Decision

The firewall guard is **defence-in-depth**, not a mandatory invariant.

- A host that cannot establish the rules **publishes the resolver anyway** and
  emits a warning naming the guard and the reason.
- A host that loses the rules on an already-published listener, and cannot repair
  them, **alerts and keeps serving**. The listener is not withdrawn and the DNS
  stack is not stopped.
- Self-healing reassertion is unchanged: recoverable drift is repaired at publish
  time and on the host's existing periodic assertion cycle.
- A platform with no iptables publishes with the warning rather than declining,
  which is the posture the container security monitor already takes there.

Containment is asserted wherever it can be, and its absence is reported rather
than enforced.

## Alternatives considered

**Keep containment mandatory, refusing and withdrawing.** Preserves the strongest
guarantee that no unguarded listener ever serves. Rejected: the guarantee is
purchased with a fleet-wide DNS outage on every path where containment is
unavailable, including an entire platform, and it is purchased against a residue
that was never established. A control whose threat model is unstated cannot
justify that blast radius.

**Drop the guard entirely.** Simplest, and defensible given the address is not
LAN-routable. Rejected: host-local and VPN-routed clients are a real residue,
the rules are cheap to assert, and their absence is worth reporting even when it
is not worth refusing over.

**Make the posture configurable.** An operator key selecting enforce-or-warn.
Rejected: it moves a judgment the architecture should settle into per-host
configuration, and the enforcing branch carries the same unjustified blast radius
wherever it is switched on.

## Consequences

- Resolution availability is never traded for containment. The failure this
  resolver topology exists to remove cannot be reintroduced by the guard meant to
  protect it.
- An unguarded listener can serve. The window is bounded by the periodic
  assertion cycle for detection, not for availability, and the operator learns of
  it through the existing failure-alert path.
- The resolver is no longer platform-gated. A host without iptables serves DNS
  with a warning, and platform-native containment becomes an additive improvement
  rather than a precondition.
- The alert path becomes load-bearing: it is the only signal that a listener is
  running unguarded, so its delivery is verified rather than assumed.

## See Also

- docs/project/adr/0003-host-published-dns-resolver.md
