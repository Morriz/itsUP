---
description:
  Acceptance scenario for the host vitals healthcheck's strike state — the periodic
  unit records the strike state its own next run reads, so a degradation reaches
  the remediation its strike count gates instead of aborting on an unwritable
  state path.
delivered_by: [fix-pi-healthcheck-writes-run-state-as-an-un]
---

# Host Vitals Healthcheck — Spec

## What it is

`bin/pi-healthcheck.sh` runs periodically under its own supervised unit and
checks host vitals — available memory, load, conntrack occupancy, root disk
use, and Docker responsiveness. When a check trips, its response is staged
rather than immediate: the maintenance-window path restarts Docker and the
itsUP stacks on the first strike and reboots on the second, and the daytime
break-glass path acts only after three consecutive strikes. Both stages are
gated on strike state that one run writes and the next run reads.

That state is what makes the staging real. A run that cannot record its strike
state cannot be counted by the next run, so every gated remediation sits behind
a counter that never advances — and because the healthy path only clears state,
the unit reports success on every run in which nothing is wrong. This spec pins
the persistence of strike state across runs so a healthcheck whose remediation
is unreachable is caught by the functional suite instead of by an outage.

The business value is that the staged remediation the unit exists to perform
actually runs when the host degrades.

### Use cases

The scenario below is bound by exactly one functional test in
`tests/functional/bin/test_pi_healthcheck_state.py`, which invokes the real
script through its own command surface against a per-test root and per-test
runtime directory, with the external commands it shells out to replaced at the
process boundary.

#### UC-HVH1: Strike state persists between runs, so a degradation reaches its remediation

```gherkin
Given the host healthcheck runs under its supervised unit identity
And a degradation has tripped a threshold whose response is gated on strike state
When the healthcheck runs twice against that degradation
Then each run records its strike state where the next run reads it
And neither run aborts before the remediation its strike count gates
```

## Canonical fields

- **Inputs** — a root holding the script and the itsUP entry point it invokes,
  the runtime directory the supervisor provisions for the unit, and a
  degradation the vitals checks report as failing.
- **Output** — strike state readable by the following run at the location the
  first run wrote it, and a run that proceeds to its gated remediation step.

## Known caveats

- The script reads Linux process and filesystem interfaces directly and shells
  out to GNU coreutils, so the scenario is exercised on Linux only. It is bound
  on the platform the unit runs on and in CI; other platforms skip it.

## See Also

- docs/project/spec/runtime-operations.md — the pi-healthcheck operation's
  trigger, responsibility, failure symptom, and operator recovery.
