---
id: third-party/systemd/systemctl-unit-introspection
type: third-party
scope: project
description: 'What systemctl documents — and does not document — for deciding whether a named unit is installed: list-unit-files and cat carry no documented exit status for a non-matching pattern, while the Unit interface''s LoadState property has a documented value set that supports a fail-closed predicate.'
---

# systemctl — Unit Introspection for an Existence Predicate

Curated for the `itsup logs` router, which must distinguish "this unit is not
installed" from "this unit is installed and quiet" before querying the journal.
Only what bears on that predicate is recorded.

## What is not documented

`systemctl(1)` describes `list-unit-files [PATTERN...]` as listing "unit files
installed on the system, in combination with their enablement state", and `cat
PATTERN...` as showing "backing files of one or more units". For **neither
command does the manual specify an exit status when the pattern matches
nothing**, and `show` documents no `--quiet`. A predicate built on the exit code
of any of the three rests on undocumented behavior.

`list-unit-files` does not require the unit to be loaded — it reads installed
files — and it lists template units in addition to instantiated ones. `cat`
carries its own caveat: it "shows the contents of the backing files on disk,
which might not match the system manager's understanding of these units if any
unit files were updated on disk and the `daemon-reload` command was not issued
since."

## What is documented — `LoadState`

`org.freedesktop.systemd1(5)` documents the Unit interface's `LoadState`
property as indicating "whether the configuration file of a unit has been
successfully loaded", with three values:

- `loaded` — the configuration was successfully loaded.
- `error` — the configuration failed to load; details are in `LoadError`.
- `masked` — the unit is currently masked (symlinked to `/dev/null` or empty).

`systemctl show UNIT --property=LoadState` prints that property. Because the
value set is documented and the property is printed rather than signalled through
an exit code, a value comparison is the one introspection path here that does not
depend on undocumented behavior.

**The fail-closed predicate this supports:** a unit is usable iff `LoadState` is
exactly `loaded`. Every other value — the documented `error` and `masked`, and any
value outside the documented set — is treated as not usable, and the observed
value is reported rather than interpreted. systemd emits `not-found` for an
absent unit in practice, but that value is absent from the documented set, so a
consumer must not assert it; matching `loaded` positively covers the case without
depending on it.

## `ActiveState` (adjacent, for reading a unit's runtime state)

Documented values: `active`, `inactive`, `failed`, `activating`, `deactivating`,
`maintenance`, `reloading`, `refreshing`. `failed` is "similar to inactive, but
the unit failed in some way (process returned error code on exit, or crashed, an
operation timed out, or after too many restarts)".

## Sources

- https://man7.org/linux/man-pages/man1/systemctl.1.html
- https://man7.org/linux/man-pages/man5/org.freedesktop.systemd1.5.html
