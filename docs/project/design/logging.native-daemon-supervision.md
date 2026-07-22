---
description: 'How itsUP produces, formats, and consumes logs — supervised daemons logging plainly to the host supervisor journal, the per-source instrukt-ai/itsup/ diagnostic folder written by interactive and one-shot processes, the Traefik access.log → CrowdSec feed, ephemeral container logs, and the instrukt-ai-logs viewer.'
---

# Logging — Design

## Purpose

itsUP runs a mix of containerized upstream services and non-containerized itsUP
code (API, monitor, CLI, backup, artifact generation). It needs a
machine-parseable access log that CrowdSec can analyze for threats, a consistent
diagnostic record across all the Python processes, and human-readable output when
an operator runs a command interactively.

The design splits emission by **audience**, not by TTY detection: human-facing
CLI output is rendered with `click` in the command/entry layer, and
diagnostic/audit output goes to whichever sink the process's execution context
owns. That sink is the second axis: a **supervised daemon** writes plain records
to its own stdout and the host supervisor owns them; an **interactive or one-shot
process** writes to its per-source file under the instrukt-ai diagnostic folder.
Traefik's access log stays file-based under `logs/`; every Docker container also
emits to Docker's json-file driver (ephemeral).

Daemon diagnostics routed through the supervisor survive a restart, rotate under
the operator's existing host policy, and are readable without knowing which user
the process ran as.

## Inputs/Outputs

**Files in `logs/` (durable, host-side):**

- `logs/access.log` — Traefik HTTP/HTTPS access log, JSON format, and nothing
  else. Traefik writes to `/var/log/traefik/access.log` inside the container;
  the proxy compose mounts the host `logs/` dir there
  (`tpl/docker-compose.yml.j2:46,88`, `proxy/docker-compose.yml:46,85`). Format
  and path are set in the Traefik config (`tpl/traefik.yml.j2:10-12`,
  `proxy/traefik/traefik.yml:11`): `accessLog.filePath:
  /var/log/traefik/access.log`, `format: json`. No itsUP process appends to it —
  it is the CrowdSec acquisition feed and stays single-writer and single-format.
- `logs/monitor.log` — the security monitor's **restart watermark**, not a
  diagnostic log. `bin/monitor.py` appends a `[<ts>] Started` marker line on each
  start, and `monitor/core.py:_get_last_processed_timestamp` reads the last such
  marker to resume connection processing from where it left off. It carries no
  diagnostic records. Path: `monitor/constants.py` (`LOG_FILE`).

**Supervised daemon logs (the host supervisor's journal):**

The API server and the container security monitor run as daemon units the host
supervisor owns. Each writes plain records to its own stdout; the supervisor
captures them, stamps time and unit identity, and applies the host's retention
policy.

- `journalctl -u itsup-api` / `journalctl -u itsup-monitor` on Linux.
- `~/Library/Logs/itsup.api.log` on macOS, where the launchd agent's
  `StandardOutPath` is the equivalent sink. The monitor has no macOS agent — it
  requires root and `iptables`, so it is Linux-only.

`lib/log_setup.py:configure_daemon_logging()` is what attaches that stdout
handler: one `StreamHandler` on the root logger, formatter `levelname logger
message` — no timestamp and no identity, because the supervisor supplies both
and duplicating them is noise. It sets the root logger to the third-party level
and the `itsup` prefix to `ITSUP_LOG_LEVEL` (bridging `LOG_LEVEL` when set),
mirroring the level split `configure_logging` applies to the file sink so a
level means the same thing in both contexts.

**Diagnostic logs (`instrukt_ai_logging`, host-side) — one folder, one file per
producing process:**

The library writes a single folder per app, `$XDG_STATE_HOME/instrukt-ai/itsup/`
(fallback `~/.local/state/instrukt-ai/itsup/`), and one plain-text logfmt file
per producing process, selected by the `source=` argument of `configure_logging`
(`configure_logging(app, *, source=None)` → `f"{source or app}.log"`, a single
file-only `WatchedFileHandler` on the root logger — the library has no console
mode, which is why the daemon paths configure their own stdout handler instead):

- `instrukt-ai/itsup/itsup.log` — the `itsup` CLI and the ephemeral CLI-family
  one-shots (`bin/migrate_to_v2.py`, `bin/write_artifacts.py`), via
  `configure_logging("itsup")` (default source).
- `instrukt-ai/itsup/backup.log` — the backup job, via
  `configure_logging("itsup", source="backup")`.

Each producing process declares its own `source`; the empty-source default (one
shared `<app>.log`) is deliberately avoided because multiple independent
processes must not share one `WatchedFileHandler` file. This mirrors TeleClaude's
convention (`configure_logging("teleclaude", source="cron")`).

**Container logs (ephemeral):** every Docker container also writes to Docker's
default json-file driver. Read via `docker logs` / `docker compose logs`. These
are not part of the `logs/` directory contract.

**Consumers:**

- **CrowdSec** reads `logs/access.log` (mounted into its container at
  `/var/log/traefik/access.log`) as a log acquisition source
  (`crowdsec/acquis.yml:8-11`, `labels.type: traefik`). This is the threat-
  detection feed.
- **`journalctl -u <unit>`** (Linux) / the agent's `StandardOutPath` file (macOS)
  — the daemon diagnostics.
- **`instrukt-ai-logs itsup`** — the logger's shipped viewer (console script
  `instrukt_ai_logging.cli:main`) tails the diagnostic folder: folder- and
  rotation-aware, with `--since`, `--include <source>`, and `--grep`. itsUP
  carries no diagnostic-log viewer of its own.
- **Operators** via direct `tail`/`zcat` (e.g. `logs/access.log` raw, or piped
  through `bin/format-logs.py`).

## Invariants

- **Emission splits into two channels by audience across every itsUP Python
  process.** Human-facing output — everything a person reads on screen — is
  emitted with `click` in the command/entry layer (`commands/`, the `bin/*`
  entry-point `main()`s), which keeps color and the `✓`/`⚠`/`✗` icons and
  auto-strips them when stdout is not a TTY. A single shared helper in
  `commands/common.py` (`ok`/`warn`/`fail`/`step`, via `click.secho`) renders
  them; no command carries its own ANSI table. Diagnostic/audit output is emitted
  with `instrukt_ai_logging` (`get_logger("itsup.<module>")`) as plain text.
  `lib/` never writes to the terminal: library functions return data or raise,
  and the calling command echoes any human-facing result.
- **The sink is chosen by execution context, not by the call site.** Every module
  acquires its logger the same way (`get_logger("itsup.<module>")`); only the
  process entry point decides where records land. A supervised daemon calls
  `configure_daemon_logging()` and its records go to stdout; the CLI and the
  one-shots call `configure_logging(...)` and their records go to the per-source
  file. No `get_logger` call site knows or cares which applies.
- **No itsUP process launches through a shell redirect.** A daemon's records
  reach durable storage because a supervisor captures its stdout, never because a
  launcher pointed `>` at a file. A restart is therefore non-destructive: the
  journal retains records written before it.
- **One diagnostic folder, one file per producing process** for the non-daemon
  paths. The file is selected by `configure_logging(source=)`, not by
  `get_logger` (which only sets the logger name → level-gating via the `itsup`
  app prefix). Loggers are acquired under the `itsup.` prefix so
  `ITSUP_LOG_LEVEL` governs them; the CLI maps `-v`/`-vv` → `ITSUP_LOG_LEVEL`
  `DEBUG`/`TRACE` before its `configure_logging` call, the one-shots bridge their
  `LOG_LEVEL` value, and the daemons get the same bridge inside
  `configure_daemon_logging()`. `.trace()` is available because `get_logger`
  returns `InstruktAILogger`.
- **`logs/access.log` has exactly one writer.** Traefik owns it, in JSON, because
  CrowdSec parses it for threat detection; a second writer in a second format
  would corrupt the feed. The API's access records go to its own journal.
- **`logs/monitor.log` is the monitor's restart watermark, not diagnostics.** The
  `[<ts>] Started` marker written by `bin/monitor.py` and read by
  `monitor/core.py:_get_last_processed_timestamp` is application state,
  independent of the diagnostic stream.
- **Operator banners stay at the entry layer.** `bin/monitor.py` and
  `bin/backup.py` startup/progress banners are emitted with `print`/`click`; only
  their diagnostic record routes to the logger.
- **The daemon record carries no timestamp and no identity; the supervisor adds
  both.** The instrukt-ai diagnostic files are plain-text logfmt and do carry
  their own timestamps, because no supervisor stamps them.
- **Container logs are ephemeral.** Removing a container discards its Docker logs;
  only the `logs/` files, the journal, and the instrukt-ai diagnostic folder
  survive container lifecycle. Durable analysis must use those.
- **Secret values never enter a log record.** Names at most, in either sink.

## Primary flows

**Reading a daemon's diagnostics:** `journalctl -u itsup-api` or `journalctl -u
itsup-monitor` (add `-f` to follow, `--since` to window). The records survive
restarts of the unit and rotate under the host's journald retention. On macOS the
API's equivalent is `~/Library/Logs/itsup.api.log`.

**Viewing CLI and one-shot diagnostics (`instrukt-ai-logs itsup [--include
<source>] [--since W] [--grep RE]`):** the shipped viewer resolves the files
under `instrukt-ai/itsup/` and follows them (rotation-aware). `--include backup`
narrows to `backup.log`; with no filter it merges every source in the folder.

**Viewing the access log:** `tail`/`zcat` on `logs/access.log`, optionally piped
through `bin/format-logs.py` for the flat human-readable line.

**Access-log formatting (`bin/format-logs.py`):** reads JSON lines from stdin and
emits a flat line: `TIME LEVEL CLIENT_IP "METHOD HOST/PATH" → SERVICE STATUS
DURATION [overhead] SIZE [retries] [TLS]` (`bin/format-logs.py:24-94`). Duration
is ns→ms (`Duration` field ÷ 1e6, `bin/format-logs.py:19-21,52-56`), the
`@docker` suffix is stripped from `ServiceName`, overhead is shown only when
> 0.5ms, and non-JSON lines pass through unchanged (`bin/format-logs.py:111-113`).

**Threat detection:** Traefik appends each request to `logs/access.log` → the
CrowdSec acquisition source (`crowdsec/acquis.yml`) parses it under the `traefik`
label for detection.

**API logging:** `api/main.py` calls `configure_daemon_logging()` before handing
control to uvicorn and runs uvicorn with its own default configuration. Three
streams result, and they are not all stdout: the application's `itsup.*` records
go to the root stdout handler; uvicorn's own server and error records go to
uvicorn's **stderr** handler (they never reach the root handler, because the
`uvicorn` logger sets `propagate: False`); its access records go to uvicorn's
stdout handler. The supervisor captures both streams, so all three land under
the API unit.

**Monitor logging:** `bin/monitor.py` calls `configure_daemon_logging()`, so its
diagnostics go to stdout and land under the monitor unit; its `[<ts>]` watermark
and operator banners are unaffected.

## Failure modes

- **Unwritable diagnostic log dir/file.** `configure_logging` treats logging as
  an essential subsystem and raises at startup if the log dir/file cannot be
  written — there is no degraded or console-fallback mode. A process that cannot
  open its file fails fast rather than starting blind. The daemon paths have no
  such failure: stdout is always available.
- **Journal retention exhausted.** journald caps its own store; once the cap is
  reached the oldest records are discarded. A host that needs a longer daemon
  history raises the cap rather than reintroducing a file sink, which would put
  history back on an unrotated path.
- **Missing watermark.** If `logs/monitor.log` is absent or has no `[<ts>]`
  marker, `monitor/core.py:_get_last_processed_timestamp` returns `None` and the
  monitor reprocesses the docker-log window from scratch — correct, just less
  efficient.
- **Malformed access-log line.** `bin/format-logs.py` catches
  `json.JSONDecodeError` and passes the raw line through (`:111-113`); a parse
  exception inside a valid JSON object yields a `[PARSE ERROR: ...]` prefix
  rather than crashing the stream (`:96-98`).
- **Container removal.** Container (Docker json-file) logs are lost when the
  container is removed; only the `logs/` files, the journal, and the instrukt-ai
  diagnostic folder persist.
