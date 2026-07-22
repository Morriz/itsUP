---
id: third-party/systemd/journalctl-querying
type: third-party
scope: project
description: Verified journalctl query semantics itsUP delegates to — the --since/--until time grammar that rejects a bare duration, the smart-case -g/--grep default and its --case-sensitive override, -n/--lines bounds, -f/--follow, and the silent success of -u on a unit with no records.
---

# journalctl — Query Semantics

Curated from the `journalctl(1)` manual page for the `itsup logs` router, which
delegates its unit-backed targets to `journalctl` rather than reading the journal
itself. Only the flags the router composes are covered.

## Time window — `--since` / `--until`

- Absolute form: `"2012-10-30 18:17:16"`. An omitted time part means `00:00:00`;
  an omitted seconds component means `:00`; an omitted date component means the
  current day.
- The keywords `yesterday`, `today`, `tomorrow`, and `now` are accepted.
- Relative offsets require a leading `-` or `+` (before/after the current
  moment), per `systemd.time(7)`.
- **A bare duration such as `10m` is not valid.** A caller offering a bare
  duration as its own surface must convert it — to `-10m`, or to an absolute
  stamp in the format above — before passing it on.

## Pattern matching — `-g` / `--grep` and `--case-sensitive`

- `-g PATTERN` filters to entries whose `MESSAGE=` matches the PERL-compatible
  pattern.
- Default is **smart-case**: "If the pattern is all lowercase, matching is case
  insensitive. Otherwise, matching is case sensitive."
- `--case-sensitive[=BOOLEAN]` overrides that default in either direction. A
  caller that needs one deterministic contract across backends sets this
  explicitly rather than inheriting smart-case.

## Bounds and streaming

- `-n`/`--lines` takes a positive integer or `all`. A `+`-prefixed number selects
  the oldest events instead of the most recent. Omitting the argument defaults to
  10.
- `-f`/`--follow` prints only the most recent entries, then continues printing new
  entries as they are appended until interrupted.

## Unit selection — `-u` / `--unit`

- `-u UNIT` shows messages for that systemd unit, or for any unit matched by a
  pattern.
- The manual documents no error for a unit that has produced no records. Exit
  status is 0 on success and non-zero only on failure, so **a query against an
  uninstalled or never-run unit succeeds with empty output** — indistinguishable
  from a healthy, quiet unit unless the caller checks unit existence separately.

## Sources

- https://man7.org/linux/man-pages/man1/journalctl.1.html
