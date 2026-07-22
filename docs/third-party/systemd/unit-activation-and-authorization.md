---
description: systemd semantics itsUP's daemon supervision depends on — that [Install]/WantedBy= only takes effect through `systemctl enable`, so an installed-but-unenabled unit never boot-activates yet is still startable on demand, and that an unprivileged caller cannot manage a system unit without polkit authorization.
---

# systemd — Unit Activation and Authorization

## What it is

itsUP's documented startup sequence is DNS → proxy → API → monitor, owned by
`itsup run` rather than by systemd targets — DNS creates the `proxynet` network
the others depend on. Any design that supervises a long-running itsUP daemon as
a systemd unit therefore has to answer two questions before it can claim that
ownership holds: how a unit becomes boot-activated (and how it can be installed
without becoming so), and who is authorized to start it. A wrong reading of
either yields units that race the orchestrated sequence, or an unattended caller
that cannot start them at all. This entry records both contracts verbatim.

## Canonical fields

### `[Install]` is inert until `systemctl enable`

> systemd does not look at the [Install] section at all during normal
> operation, so any directives in that section only have an effect through the
> symlinks created during enablement.

`WantedBy=` lives in `[Install]`. Enabling a unit creates a symlink in the
target's `.wants/` directory, and that symlink is the entire mechanism by which
the unit is pulled in at boot. Consequences:

- A unit file that is installed and `daemon-reload`ed but **never enabled** has
  no `.wants/` symlink, so nothing activates it at boot.
- The same unit is still fully startable on demand with `systemctl start` —
  enablement governs automatic activation, not invocability.

This is the seam that lets one path own startup: install the unit definitions
without enabling them, and the only thing that ever starts them is the
orchestrator, in its own order.

### `enable` does not start; `enable --now` does both

> Note that this does *not* have the effect of also starting any of the units
> being enabled. If this is desired, combine this command with the **--now**
> switch, or invoke **start** with appropriate arguments later.

`enable --now` is therefore two decisions in one flag — boot activation *and*
immediate start. A unit whose lifecycle belongs to an orchestrator wants
neither.

### `daemon-reload` is what makes a new unit file visible

> Reload the systemd manager configuration. This will rerun all generators,
> reload all unit files, and recreate the entire dependency tree.

A newly written unit file is not known to the manager until this runs. It does
not start, enable, or restart anything.

### Managing a system unit as a non-root caller requires polkit authorization

Operations that modify unit state — `StartUnit()`, `StopUnit()`,
`RestartUnit()`, `KillUnit()` and similar — require the polkit action
`org.freedesktop.systemd1.manage-units`. PID 1 uses polkit to allow privileged
operations for unprivileged processes, and the action carries a `verb` detail
naming which of `start`, `stop`, `reload`, `restart`, `try-restart`,
`reload-or-restart`, `reload-or-try-restart`, `kill`, `reset-failed` or
`set-property` is being attempted.

An unprivileged `systemctl start` on a system unit therefore triggers an
authentication prompt (`==== AUTHENTICATING FOR
org.freedesktop.systemd1.manage-units ====`) unless a polkit rule grants the
action. Granting it means shipping a rules file (e.g.
`/etc/polkit-1/rules.d/60-*.rules`) that matches the action, the unit names, and
the caller's group.

The load-bearing consequence for an unattended caller: there is no interactive
agent to answer that prompt. A boot-time or timer-driven invocation running as
an unprivileged user does not "sometimes" succeed — it has no authorization path
at all unless one was explicitly installed.

## Known caveats

- **`enable --now` on a unit an orchestrator also starts creates two owners.**
  The unit can be pulled in by its target at boot *and* started by the
  orchestrator, in either order, defeating any sequence the orchestrator
  enforces.
- **"It works when I run it" is not evidence for the unattended path.** An
  operator testing `systemctl start` from an interactive login has a polkit
  agent available; the same command from a non-interactive unit does not.
  Authorization must be verified on the unattended caller, not the shell.
- **Passwordless `sudo` and a polkit rule are different grants.** A host that
  already permits passwordless `sudo` for the service account needs no polkit
  rule if every system-unit verb goes through `sudo`; adding a polkit rule as
  well widens the surface for no gain.

## Sources

- https://man7.org/linux/man-pages/man5/systemd.unit.5.html
- https://man7.org/linux/man-pages/man1/systemctl.1.html
- https://man7.org/linux/man-pages/man5/org.freedesktop.systemd1.5.html
