---
description:
  Acceptance scenario for the host vitals healthcheck's strike state — the periodic
  unit records the strike state its own next run reads, so a degradation reaches
  the remediation its strike count gates instead of aborting on an unwritable
  state path.
---

# Host Vitals Healthcheck — Spec

## Required reads

- @docs/project/spec/runtime-operations.md

## What it is

`bin/pi-healthcheck.sh` runs periodically under its own supervised unit and
checks host vitals — available memory, load, conntrack occupancy, root disk
use, and Docker responsiveness. When a check trips, its response is staged
rather than immediate: the maintenance-window path restarts Docker and the
itsUP stacks on the first strike and reboots on the second, and the daytime
break-glass path acts only after three consecutive strikes. Both stages are
gated on strike state that one run writes and the next run reads.

The healthy path clears strike state and reports success. A run whose strike
state is not recorded is indistinguishable from a healthy run.

The business value is that the staged remediation the unit exists to perform
actually runs when the host degrades.

### Use cases

The scenario below is bound by exactly one functional test in
`tests/operations/test_host_vitals_healthcheck.py`, which invokes the real
script through its own command surface against a per-test root and per-test
runtime directory, with the external commands it shells out to replaced at the
process boundary.

#### UC-HVH1: A second run reads the first run's strike state and escalates

```gherkin
Given the host healthcheck runs under its supervised unit identity
And a degradation has tripped a threshold inside the maintenance window
When the healthcheck runs twice against that degradation
Then the first run records its strike state and restarts Docker and the itsUP stacks
And the second run reads that state and reboots the host
```

## Canonical fields

- **Inputs** — a root holding the script and the itsUP entry point it invokes,
  the runtime directory the supervisor provisions for the unit, and a
  degradation the vitals checks report as failing.
- **Output** — strike state readable by the following run at the location the
  first run wrote it, and a run that proceeds to its gated remediation step.

## Known caveats

- The script reads Linux process interfaces and GNU coreutils behaviour through
  the commands it invokes. The scenario is exercised with those commands
  replaced at the process boundary, so it runs on every platform the suite runs
  on rather than only on the unit's own.

## See Also

- docs/project/spec/runtime-operations.md — the pi-healthcheck operation's
  trigger, responsibility, failure symptom, and operator recovery.
