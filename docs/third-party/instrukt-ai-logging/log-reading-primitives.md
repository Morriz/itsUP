---
id: third-party/instrukt-ai-logging/log-reading-primitives
type: third-party
scope: project
description: Verified read-side contracts of the installed instrukt-ai-logging package that itsUP reuses — parse_since duration grammar, the rotation-aware iter_follow_lines follower, and why iter_recent_log_lines_merged cannot window Traefik's JSON access log.
---

# instrukt-ai-logging — Read-Side Primitives

Curated from the installed package
(`.venv/lib/python3.14/site-packages/instrukt_ai_logging/`) for the `itsup logs`
router, which reuses the library's readers rather than re-deriving them. The
write side (`configure_logging`, `get_logger`) is covered by
`project/design/logging`; only what the router consumes is recorded here.

## Export surface

`instrukt_ai_logging.__all__` exports the write side plus `resolve_log_file` /
`resolve_log_files`. The three read primitives below are **not** in `__all__`;
the package's own shipped viewer (`instrukt_ai_logging.cli:main`) imports them
from `instrukt_ai_logging.logging` and `instrukt_ai_logging.cli` directly, which
is the same import path a consumer must use. Treat them as a supported-by-usage
surface, not a declared public API: a package upgrade can move them without a
deprecation cycle.

## `logging.parse_since(value: str) -> timedelta`

- Accepts `<non-negative integer><unit>` where unit is one of `s`, `m`, `h`, `d`
  (case-insensitive, surrounding whitespace stripped). The number part is
  validated with `str.isdigit()`, so `0s` is accepted and yields a zero window;
  a sign or a decimal point is rejected.
- Raises `ValueError` on an empty string, a non-digit number part, or an
  unrecognised unit.
- Returns a `timedelta` only — it never formats a timestamp, so a consumer
  targeting a backend with its own time grammar does that conversion itself.

## `cli.iter_follow_lines(log_file, *, poll_interval_s=0.25, start_at_end=True, max_lines=None, max_seconds=None)`

- Yields lines appended to a file, `tail -f` style, by polling.
- Waits for the file to appear if it does not exist yet.
- Detects **rotation** (inode change — reopens and reads the new file from the
  start) and **truncation** (offset beyond size — seeks back to the start).
- `max_lines` / `max_seconds` bound the generator.

## `logging.iter_recent_log_lines_merged(files, since: timedelta)`

- Merges multiple files into one chronologically ordered stream, skipping files
  whose mtime predates the cutoff.
- Keys entirely on `parse_log_timestamp`, which reads the **first
  whitespace-delimited token** of each line and requires the form
  `YYYY-MM-DDTHH:MM:SS.mmmZ`. A line without that leading token inherits the
  previous parsed timestamp from its own file.
- **Not usable for Traefik's JSON access log**: those lines begin with `{`, carry
  their time inside a `time` / `StartUTC` field, and therefore have no leading
  token to parse. A consumer windowing that format supplies its own predicate over
  the JSON field.

Verified directly against the installed package source in this repository's
`.venv` — `instrukt_ai_logging/logging.py`, `instrukt_ai_logging/cli.py`, and
`instrukt_ai_logging/__init__.py`.
