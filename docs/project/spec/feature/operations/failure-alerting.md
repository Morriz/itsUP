---
description: Acceptance scenarios for itsUP's transport-agnostic ops failure alerting — the supervisor failure hook that announces a failed unit exactly once through an operator-configured command, the clean no-op when no command is configured, and the deadman assertion that catches a nightly apply that never succeeded.
delivered_by: [ops-failure-alerting]
---

# Failure Alerting — Spec

## What it is

An unattended failure that nobody sees is indistinguishable from health. itsUP's
scheduled and supervised units announce their own failures: the supervisor's
failure hook runs an alert composer that gathers the failed unit's identity and
its recent journal context and hands the result to a command the operator
configures. itsUP emits the event; the operator owns the transport, so no
transport or product name appears in this repository.

The failure hook cannot see the failure class where the unit never ran at all — a
masked unit, or a timer that never fired. A deadman assertion covers that class by
asserting the age of the last successful nightly apply.

Alerting is a Linux/systemd capability. The configuration surface and the alert
command contract are specified in `project/spec/itsup-config`; the operations it
covers are listed in `project/spec/runtime-operations`.

### Use cases

#### UC-OFA1: A failed unit alerts exactly once through the configured command

```gherkin
Given an alert command is configured
When a covered unit fails once
Then the configured command runs exactly once
And it receives the alert body on standard input
And the body identifies the failed unit and carries its recent journal context
```

#### UC-OFA2: No configured alert command is a clean no-op

```gherkin
Given no alert command is configured
When a covered unit fails
Then no external command runs
And the composer records the suppressed alert in the journal
And it exits successfully
```

#### UC-OFA3: A successful run produces no alert

```gherkin
Given an alert command is configured
When a covered unit completes successfully
Then no alert is composed and the configured command does not run
```

#### UC-OFA4: A secret value in the command template cannot inject arguments

```gherkin
Given an alert command template references a secret placeholder
And the secret's value contains shell metacharacters and whitespace
When the composer runs the command
Then the value arrives as a single argument of the invoked command
And no additional argument or command is produced from it
```

#### UC-OFA5: A stale last-successful-apply trips the deadman assertion

```gherkin
Given the recorded last successful nightly apply is older than the expected window
When the deadman assertion runs
Then an alert is composed naming the stale apply and the age observed
And a repeat assertion within the same stale period composes no further alert
```

#### UC-OFA6: A fresh last-successful-apply keeps the deadman silent

```gherkin
Given the recorded last successful nightly apply is within the expected window
When the deadman assertion runs
Then no alert is composed
```

## Canonical fields

This spec pins the acceptance scenarios only. The `alert` configuration key, its
command-template contract, and the placeholder-resolution rules are specified in
`project/spec/itsup-config`. The units covered by the failure hook, the deadman's
expected window, and the operator's first checks are specified in
`project/spec/runtime-operations`.

## See Also

- docs/project/spec/itsup-config.md
- docs/project/spec/runtime-operations.md
- docs/project/spec/environment-variables.md
