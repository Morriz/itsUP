---
id: third-party/instruktai-python-logger/logging-api
type: third-party
scope: project
description: 'instruktai-python-logger (import module instrukt_ai_logging) 0.6.1 — the configure_logging/get_logger contract, the per-source file model, XDG log paths, level env vars, and the instrukt-ai-logs viewer. Verified against source at ~/Workspace/InstruktAI/python-logger.'
---

# instruktai-python-logger — Third-Party Reference

## What it is

The shared InstruktAI logging standard. PyPI package `instruktai-python-logger`;
import module `instrukt_ai_logging`. Provides logfmt-formatted, per-process file
logging with dual-level control (app vs third-party) and a shipped log viewer.
Facts below are verified against the source at
`~/Workspace/InstruktAI/python-logger/instrukt_ai_logging/logging.py` at version
0.6.1.

## Canonical fields

### File model — one folder per app, one file per producing process

- `configure_logging(name, *, source=None, max_message_chars=4000) -> Path`.
  Configure once at process start. The log filename is `f"{source or app}.log"`
  installed as a single `WatchedFileHandler` on `logging.root` (file-only, **no
  console handler**). Returns the resolved log file path.
- **The file is selected by `source=`, not by `get_logger`.** `source` is the
  logical identity of the producing process within the app. Omitted → the
  canonical `<app>.log`. Provided (e.g. `source="monitor"`) → `<source>.log`.
- `get_logger(name) -> InstruktAILogger` only sets the logger *name*; it never
  selects a file. `InstruktAILogger` subclasses `logging.Logger`, accepts
  arbitrary `**kv` structured fields, supports `%`-style args, and provides a
  `TRACE` level and a `.trace()` method.
- Log folder: `$XDG_STATE_HOME/instrukt-ai/<app>/` (fallback
  `~/.local/state/instrukt-ai/<app>/`). Override the root with
  `INSTRUKT_AI_LOG_ROOT`.
- **Multi-process footgun:** the empty-`source` default silently routes every
  configuring process to the shared `<app>.log`. Distinct long-running processes
  (daemons, periodic jobs) must each pass their own `source`, or they collide on
  one `WatchedFileHandler` file. Small single-process apps may leave `source`
  empty. (Flagged upstream; the API does not warn.)

### Level control (env, read at `configure_logging` call time)

- `{PREFIX}_LOG_LEVEL` — level for our loggers (those under the app prefix).
  `configure_logging("itsup")` normalizes to prefix `ITSUP` → reads
  `ITSUP_LOG_LEVEL` (default INFO). Only loggers named under the app prefix
  (`itsup`, `itsup.*`) inherit the app level; root stays at the third-party level.
  Acquire app loggers as `get_logger("itsup.<module>")` so the app level governs
  them.
- `{PREFIX}_THIRD_PARTY_LOG_LEVEL` (default WARNING), `{PREFIX}_THIRD_PARTY_LOGGERS`
  (spotlight prefixes), `{PREFIX}_MUTED_LOGGERS` (forced to WARNING+).
- Format: logfmt `key=value`. Levels: TRACE (high-volume chatter) < DEBUG
  (successful outcomes) < INFO (business events) < WARNING < ERROR/CRITICAL.

### Path resolution helpers

- `resolve_log_file(app_name, *, source=None) -> Path` — the file for an
  app/source (same rule as `configure_logging`).
- `resolve_log_files(app_name, *, stems=None) -> list[Path]` — every `<stem>.log*`
  in the app's folder (rotation suffixes included), optionally filtered by stems.

### Viewer — the shipped console script

- `instrukt-ai-logs <app> [--since W] [--include <stem>] [--grep RE] [--exclude RE]`
  (entry point `instrukt_ai_logging.cli:main`). Folder- and rotation-aware
  follow/tail over the app's diagnostic folder; `--include <source>` narrows to
  one source file, no filter merges all. Default window `--since 10m`.
- Python follow/read APIs are exposed for programmatic use: `iter_follow_lines`,
  `iter_recent_log_lines_merged`, `parse_since` (in `instrukt_ai_logging.cli` /
  `.logging`).

### Failure behavior

- Logging is treated as an essential subsystem: an unwritable log dir/file raises
  at `configure_logging` startup. There is no degraded or stderr-fallback mode.
- Rotation bootstrap problems are surfaced as a warning, never fatal to an
  already-working file.
