---
description: Acceptance scenarios for container name resolution on an itsUP container host — every container resolves internal and external names through the host's own logged resolver regardless of its ingress or egress declarations, the resolver stays unreachable from outside the host, and a host platform that cannot establish the resolver says so in its own terms instead of surfacing a raw runtime error.
delivered_by:
  - macos-container-host-dns-support
---

# Container Name Resolution — Spec

## What it is

itsUP gives every containerized service one resolver to ask, owned by the
container host and reachable from the container's own network namespace. The
capability is deliberately independent of network membership: a service that
network segmentation leaves isolated — no ingress row, no egress declaration —
resolves exactly as well as a publicly routed one. That independence is the
whole point, because the alternative is granting shared-network membership to
every service that needs to look a name up, which is the lateral-movement
surface segmentation exists to close.

The resolver is also the platform's evidence surface. Every query a container
makes is recorded at the host, and the security monitor treats that record as
the test of whether an outbound destination was legitimately resolved or reached
by a hardcoded address. A host that resolves without recording delivers half the
capability.

The business value is that an operator can add a container host to the fleet and
expect both halves to hold on it: services resolve, and what they resolved is
observable. Where a host platform cannot deliver a half, it says so plainly —
naming the platform limitation and what is consequently not in force — rather
than failing with a runtime error the operator has to decode, or succeeding
silently with a guarantee that is not actually there.

Container host platforms differ in what they can offer. A host whose container
runtime shares the host's own network stack can both serve and contain the
resolver at the host boundary. A host whose runtime runs behind a virtual
machine boundary reaches the resolver differently and contains it differently,
because the boundary itself is a layer. The scenarios below are written against
the operator-observable outcome, so a platform satisfies them however its
runtime is shaped.

### Use cases

#### UC-CNR1: An isolated container resolves internal and external names

```gherkin
Given a container host running the itsUP stack
And a container whose project declares neither an ingress row nor an egress target
When that container resolves a sibling service name and a public name
Then both resolve successfully
```

#### UC-CNR2: Container queries are recorded at the host resolver

```gherkin
Given a container host running the itsUP stack
When a container resolves a name
Then that name appears in the host resolver's query record
```

#### UC-CNR3: Bringing the stack up leaves the resolver serving

```gherkin
Given a supported container host with the itsUP stack not running
When the operator brings the stack up
Then bringup completes
And containers resolve names without further operator intervention
```

#### UC-CNR4: The container resolver is not answerable from outside the host

```gherkin
Given a container host running the itsUP stack
When another machine on the local network queries the container resolver's address
Then it receives no answer from that resolver
```

#### UC-CNR5: The operator can read the host's resolver and containment state

```gherkin
Given a container host running the itsUP stack
When the operator asks the host for its runtime status
Then the report states whether the container resolver is serving
And states whether containment of that resolver is established
And every surface it reads to decide exists on that host's platform
```

#### UC-CNR6: A containment loss reaches the operator unprompted

```gherkin
Given a container host serving container DNS
When containment of the resolver is absent or lost and cannot be restored
Then the operator is notified without having inspected the host
And the resolver keeps serving
```

#### UC-CNR7: An unsupported resolver path is refused in platform terms

```gherkin
Given a container host whose platform cannot establish the container resolver as configured
When the operator brings the stack up
Then the failure names the platform limitation and the capability that is unavailable
And the operator is not left to interpret a raw container runtime error
```

#### UC-CNR8: Adding a host platform does not change an existing one

```gherkin
Given a container host on a platform that already served container DNS
When support for an additional host platform is delivered
Then resolution, recording, containment, and operator reporting on the existing platform are unchanged
```

## Canonical fields

The capability has no operator-authored configuration surface. The resolver's
address is derived by the platform, not declared by an operator, and a project's
`itsup-project.yml` carries no key that opts into or out of it — which is what
makes UC-CNR1 hold for a project that declares nothing at all.

What a host platform contributes is therefore not configuration but capability,
and the operator-visible facts are:

- **Whether the resolver is serving** on this host — the subject of UC-CNR3 and
  reported by UC-CNR5.
- **Whether containment is established** on this host — reported by UC-CNR5 and,
  when it is lost, delivered unprompted by UC-CNR6. Containment is
  defence-in-depth: its absence is reported, never enforced by withdrawing the
  resolver.
- **Whether the platform can serve the resolver at all** — when it cannot,
  UC-CNR7 governs what the operator is told.

## Known caveats

- **The query record's consumer is platform-dependent.** UC-CNR2 requires the
  record to exist, not that anything reads it. On a host platform where the
  security monitor does not run, the evidence is produced and unconsumed, so the
  monitor's guarantee is not in force there even though resolution and recording
  are. UC-CNR5 is what makes that state legible to the operator rather than
  assumed.
- **UC-CNR6's notification path is itself platform-dependent.** A host platform
  whose supervisor offers no failure hook needs another route to satisfy this
  scenario; the scenario is not weakened for such a platform, because an
  unreported containment loss is the exact condition it exists to prevent.

## See Also

- docs/project/design/deployment-orchestration.md
- docs/project/design/security-architecture.md
- docs/project/spec/runtime-operations.md
