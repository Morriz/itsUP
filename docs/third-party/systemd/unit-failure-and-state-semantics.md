---
description: systemd semantics itsUP's failure alerting depends on — what OnFailure= actually triggers on (the failed state, not a crash), how Restart= plus the start limit delays that trigger, template-instance specifiers, ExecStartPost= ordering under Type=oneshot, and StateDirectory= creation timing and ownership.
---

# systemd — Unit Failure and State Semantics

## What it is

itsUP's ops failure alerting is built entirely on the supervisor's own
mechanisms rather than a polling daemon. That makes the exact semantics of four
systemd directives load-bearing: a wrong reading produces alerts that never fire,
fire late, or fire on the wrong event. These are the verbatim contracts from the
systemd manual pages.

## Canonical fields

### `OnFailure=` triggers on the failed state, not on a crash

> A space-separated list of one or more units that are activated when this unit
> enters the "failed" state.

The trigger is the **unit result state**, not the exit of a process. Two
consequences itsUP depends on:

- A unit that exits successfully never enters `failed`, so success silence is
  structural — no code decides not to alert.
- A unit that crashes but is restarted does **not** necessarily enter `failed`.
  See the start-limit interaction below.

`OnSuccess=` (systemd 249+) is the mirror, activating when the unit enters
`inactive`. itsUP does not use it: success notifications train operators to
ignore the channel.

### `Restart=` plus the start limit delays when `failed` is reached

> Note that units which are configured for `Restart=`, and which reach the start
> limit are not attempted to be restarted anymore; however, they may still be
> restarted manually or from a timer or socket at a later point, after the
> interval has passed.

For a unit with `Restart=always` or `Restart=on-failure`, a single crash is
followed by a restart attempt, not by the `failed` state. The unit reaches
`failed` — and therefore fires `OnFailure=` — only once it exhausts
`StartLimitBurst` attempts within `StartLimitIntervalSec`. An always-restarting
daemon therefore alerts on **sustained** failure, not on the first crash, and the
alert latency is a function of those two settings.

A unit with no `Restart=` (such as a `Type=oneshot` scheduled job) enters
`failed` on its first non-zero exit, so its hook fires immediately.

### Template instances and the `%n` / `%i` specifiers

In a template unit, the instance parameter is referred to with `%i` — the name
between `@` and the type suffix. `%n` expands to the full unit name of the unit
being processed.

`OnFailure=alert@%n.service` on a failing unit therefore instantiates the alert
template with the failing unit's own full name as the instance, which the alert
unit reads back as `%i`. Because `%n` already includes the `.service` suffix, the
resulting instance name carries it too.

### `ExecStartPost=` ordering

`ExecStartPost=` commands run after the commands in `ExecStart=` have completed
successfully. For `Type=oneshot` this makes `ExecStartPost=` a success-conditional
step: it does not run when `ExecStart=` fails. That property is what lets a
success-only stamp be expressed in the unit rather than in application code.

### `StateDirectory=` creation timing and ownership

> The directories specified with `StateDirectory=` ... are not removed when the
> unit is stopped.

Creation is per-unit and start-time scoped: when **the unit** is started, the
named directories are created including their parents, below `/var/lib/` for
system units. The innermost directories are owned by the unit's `User=` and
`Group=`, with mode from `StateDirectoryMode=`. The full path is exported to the
unit as `$STATE_DIRECTORY`.

The load-bearing consequence: declaring `StateDirectory=` on one unit does **not**
make the directory exist for a different unit. Every unit that writes into the
shared state directory declares it, or the directory must be created by something
that runs before all of them.

### `RuntimeDirectory=` and `RuntimeDirectoryPreserve=`

The runtime counterpart of `StateDirectory=`, for state that should not survive
indefinitely.

> In case of `RuntimeDirectory=` the innermost subdirectories are removed when the
> unit is stopped. It is possible to preserve the specified directories in this case
> if `RuntimeDirectoryPreserve=` is configured to `restart` or `yes`.

Documented behaviour:

- Directories are created below `/run/` for system units when **the unit starts**,
  and "the innermost specified directories will be owned by the user and group
  specified in `User=` and `Group=`". This is what makes a path beneath `/run`
  writable by an unprivileged unit, which bare `/run` is not.
- The full paths are exported to the unit as `$RUNTIME_DIRECTORY`.
- `RuntimeDirectoryPreserve=` takes `no` (default — removed when the unit stops),
  `restart` (preserved across a restart), or `yes` (preserved when the unit stops).
  For a repeatedly-invoked `Type=oneshot` unit, `yes` is what keeps a marker alive
  between invocations, since every invocation ends with the unit stopping.

## Known caveats

- **A directive on unit A creates nothing for unit B.** `StateDirectory=` is
  scoped to the units that declare it. A second writer that never declares it
  finds no directory on a fresh host.
- **A restart interval shorter than the start-limit window makes a unit
  structurally unalertable.** The limit trips only when `StartLimitBurst` starts
  fall inside a single `StartLimitIntervalSec`: "units which are started more than
  burst times within an interval time span are not permitted to start any more."
  With the upstream defaults (10s interval, 5 starts) and `RestartSec=5`, roughly
  two starts land in any interval, the burst never accumulates, and a persistently
  crash-looping unit restarts forever without ever entering `failed` — so
  `OnFailure=` never fires for it. Reaching `failed` requires an interval long
  enough to accumulate `StartLimitBurst` restarts at the configured `RestartSec`
  (for example `StartLimitIntervalSec=300` with `StartLimitBurst=5` at
  `RestartSec=5`, which reaches `failed` in roughly 30s of looping while leaving an
  isolated crash below the threshold). Nothing in a unit that gets this wrong looks
  incorrect; the alert simply never arrives.
- **`OnFailure=` latency is not uniform across unit types.** Oneshot jobs alert on
  first failure; always-restarting daemons alert only after the start limit is
  exhausted. Alert-trigger documentation that says "once per failure" is wrong for
  the second class.
- **Reboot lifetime of `RuntimeDirectory=` is not stated by `systemd.exec(5)`.**
  The page documents creation on start and removal on stop (modulo
  `RuntimeDirectoryPreserve=`), and says nothing about reboot. A design that relies
  on runtime state being *gone* after a reboot is relying on `/run` being volatile,
  which is a property of the host's filesystem layout rather than of these
  directives — verify it on the target host instead of inferring it from this page.
- **Timer units reach `failed` through their own faults** (for example an invalid
  calendar specification), not through the failure of the service they trigger —
  that failure belongs to the service unit. A hook on a timer and a hook on its
  service cover different events.

## Sources

- https://man7.org/linux/man-pages/man5/systemd.unit.5.html
- https://man7.org/linux/man-pages/man5/systemd.exec.5.html
- https://man7.org/linux/man-pages/man5/systemd.service.5.html
