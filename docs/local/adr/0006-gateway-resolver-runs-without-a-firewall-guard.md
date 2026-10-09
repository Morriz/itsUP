---
description: 'itsUP publishes the DNS honeypot on the proxynet gateway address with no firewall guard, because the address is not LAN-routable, the clients a guard would exclude gain only a logging forwarder, and the guard''s privileged machinery adds more surface than it removes.'
date: '2026-10-09'
number: 6
---

# The Gateway Resolver Runs Without a Firewall Guard — ADR

## Context

ADR-0003 publishes the DNS honeypot on `172.20.0.1:53`, the proxynet gateway
address, so every container reaches one logged resolver from its own network
namespace. ADR-0005 kept an iptables guard around that listener as
defence-in-depth and rejected dropping it, on two grounds: host-local and
VPN-routed clients are a real residue, and the rules are cheap to assert.

Neither ground survives inspection of what was built to satisfy them.

- **The residue gains nothing harmful.** `172.20.0.1` is not routable from the
  LAN. The clients the guard would exclude beyond that are processes on the host
  itself and clients routed in over the host's VPN interface. What they reach is
  a forwarding resolver with caching disabled that logs every query it answers.
  That is not an open resolver on the LAN, and it exposes no data and grants no
  capability those clients lack.
- **The rules are not cheap.** Asserting them from the unprivileged publish path
  required a root-owned helper installed outside the repository, a sudoers grant
  for its exact command form, a root systemd unit, a periodic reassertion hook in
  the healthcheck, and a refactor of the security monitor's iptables cleanup so
  the two owners could coexist. A passwordless-root grant is itself attack
  surface, and the whole assembly exists to fence a listener that answers only
  hosts already trusted to reach the host.

The guard therefore protects nothing material, and the machinery it needs is the
larger risk.

## Decision

The gateway-published resolver runs with no firewall guard. No iptables rules,
privileged helper, sudoers grant, systemd unit, or periodic reassertion
accompanies the listener. Its exposure is bounded by addressing alone: it is
published only on the non-LAN-routable proxynet gateway address, never on a LAN
or wildcard address.

## Alternatives Considered

**Keep the guard as defence-in-depth (ADR-0005).** Reports an unguarded
listener and narrows the client set. Rejected: the narrowed set gains nothing
harmful from the listener, while the guard's passwordless-root path and its
coupling to the security monitor's cleanup are standing surface added to defend
against that set.

**Make the guard optional per host.** An operator key enabling it. Rejected: it
keeps the privileged machinery in the codebase for a protection with no
established threat, and moves an architectural judgment into per-host
configuration.

## Consequences

- Publishing the resolver needs no privilege beyond running the DNS stack, and
  the security monitor's iptables ownership stays exclusive.
- Host-local processes and VPN-routed clients can resolve names through the
  honeypot. Their queries appear in its log alongside container queries.
- The listener's exposure depends on its bind address. Publishing it on a
  LAN-routable or wildcard address would turn it into an open resolver on that
  network, so the gateway-only bind is load-bearing.

## See Also

- docs/local/adr/0003-host-published-dns-resolver.md
- docs/local/adr/0005-dns-guard-is-defence-in-depth.md
