---
description: 'How itsUP produces, formats, and consumes logs — the file-based logs/ directory (Traefik access log, API log, monitor restart-watermark), the per-source instrukt-ai/itsup/ diagnostic folder written by every itsUP Python process, the access.log → CrowdSec feed, ephemeral container logs, and the instrukt-ai-logs viewer.'
---

# Logging — Design

## Purpose

itsUP runs a mix of containerized upstream services and non-containerized itsUP
code (API, monitor, CLI, backup, artifact generation). It needs a machine-parseable
access log that CrowdSec can analyze for threats, a consistent diagnostic record
across all the Python processes, and human-readable output when an operator runs a
command interactively.

The design splits emission by **audience**, not by TTY detection: human-facing CLI
output is rendered with `click` in the command/entry layer, and diagnostic/audit
output is written by `instrukt_ai_logging` to a per-process file. Traefik's access
log and the API log remain file-based under `logs/`; every Docker container also
emits to Docker's json-file driver (ephemeral).

## Inputs/Outputs

**Files in `logs/` (durable, host-side):**

- `logs/access.log` — Traefik HTTP/HTTPS access log, JSON format. Traefik writes
  to `/var/log/traefik/access.log` inside the container; the proxy compose mounts
  the host `logs/` dir there (`tpl/docker-compose.yml.j2:46,88`,
  `proxy/docker-compose.yml:46,85`). Format and path are set in the Traefik
  config (`tpl/traefik.yml.j2:10-12`, `proxy/traefik/traefik.yml:11`):
  `accessLog.filePath: /var/log/traefik/access.log`, `format: json`. The API also
  defines an `access` handler targeting `logs/access.log` (`api-log.conf.yaml`),
  so the uvicorn access logger can append to the same file.
- `logs/api.log` — FastAPI/uvicorn server log. Configured by `api-log.conf.yaml`
  (the `default` handler, `logging.FileHandler`, `filename: logs/api.log`,
  lines 11-15), wired into uvicorn via `log_config="api-log.conf.yaml"` in
  `api/main.py:153`.
- `logs/monitor.log` — the security monitor's **restart watermark**, not a
  diagnostic log. `bin/monitor.py` appends a `[<ts>] Started` marker line on each
  start, and `monitor/core.py:_get_last_processed_timestamp` reads the last such
  marker to resume connection processing from where it left off. It carries no
  diagnostic records; the monitor's diagnostics go to the instrukt-ai file below.
  Path: `monitor/constants.py` (`LOG_FILE`).

**Diagnostic logs (`instrukt_ai_logging`, host-side) — one folder, one file per
producing process:**

The library writes a single folder per app, `$XDG_STATE_HOME/instrukt-ai/itsup/`
(fallback `~/.local/state/instrukt-ai/itsup/`), and one plain-text logfmt file per
producing process, selected by the `source=` argument of `configure_logging`
(`configure_logging(app, *, source=None)` → `f"{source or app}.log"`, a single
file-only `WatchedFileHandler` on the root logger — no console output):

- `instrukt-ai/itsup/itsup.log` — the `itsup` CLI and the ephemeral CLI-family
  one-shots (`bin/migrate_to_v2.py`, `bin/write_artifacts.py`), via
  `configure_logging("itsup")` (default source).
- `instrukt-ai/itsup/monitor.log` — the security monitor daemon, via
  `configure_logging("itsup", source="monitor")`.
- `instrukt-ai/itsup/backup.log` — the backup job, via
  `configure_logging("itsup", source="backup")`.

Each producing process declares its own `source`; the empty-source default (one
shared `<app>.log`) is deliberately avoided for the daemons because multiple
independent processes must not share one `WatchedFileHandler` file. This mirrors
TeleClaude's convention (`configure_logging("teleclaude", source="cron")`).

**Container logs (ephemeral):** every Docker container also writes to Docker's
default json-file driver. Read via `docker logs` / `docker compose logs`. These
are not part of the `logs/` directory contract.

**Consumers:**

- **CrowdSec** reads `logs/access.log` (mounted into its container at
  `/var/log/traefik/access.log`) as a log acquisition source
  (`crowdsec/acquis.yml:8-11`, `labels.type: traefik`). This is the threat-
  detection feed.
- **`instrukt-ai-logs itsup`** — the logger's shipped viewer (console script
  `instrukt_ai_logging.cli:main`) tails the diagnostic folder: folder- and
  rotation-aware, with `--since`, `--include <source>`, and `--grep`. itsUP
  carries no diagnostic-log viewer of its own.
- **Operators** via direct `tail`/`zcat` (e.g. `logs/access.log` raw, or piped
  through `bin/format-logs.py`).

## Invariants

- **Emission splits into two channels by audience across every itsUP Python
  process.** Human-facing output — everything a person reads on screen — is emitted
  with `click` in the command/entry layer (`commands/`, the `bin/*` entry-point
  `main()`s), which keeps color and the `✓`/`⚠`/`✗` icons and auto-strips them when
  stdout is not a TTY. A single shared helper in `commands/common.py`
  (`ok`/`warn`/`fail`/`step`, via `click.secho`) renders them; no command carries
  its own ANSI table. Diagnostic/audit output is emitted with `instrukt_ai_logging`
  (`get_logger("itsup.<module>")`), plain-text logfmt, to the process's per-source
  file only — never to the terminal. `lib/` never writes to the terminal: library
  functions return data or raise, and the calling command echoes any human-facing
  result.
- **One diagnostic folder, one file per producing process.** The file is selected
  by `configure_logging(source=)`, not by `get_logger` (which only sets the logger
  name → level-gating via the `itsup` app prefix). Loggers are acquired under the
  `itsup.` prefix (`get_logger("itsup.<module>")`) so `ITSUP_LOG_LEVEL` governs
  them; the CLI maps `-v`/`-vv` → `ITSUP_LOG_LEVEL` `DEBUG`/`TRACE` before its
  `configure_logging` call, and the daemons bridge their existing `LOG_LEVEL`
  environment value into `ITSUP_LOG_LEVEL`. `.trace()` is available because
  `get_logger` returns `InstruktAILogger`.
- **`logs/monitor.log` is the monitor's restart watermark, not diagnostics.** The
  `[<ts>] Started` marker written by `bin/monitor.py` and read by
  `monitor/core.py:_get_last_processed_timestamp` is application state; it is
  independent of the diagnostic stream, which lands in
  `instrukt-ai/itsup/monitor.log`.
- **Operator banners stay at the entry layer.** `bin/monitor.py` and
  `bin/backup.py` startup/progress banners are supervised-process output
  (journald / launchd-captured / discarded when daemonized) emitted with
  `print`/`click`; only their diagnostic record routes to the logger file.
- **The API/access log format is uvicorn's, not itsUP's.** The API process is
  configured entirely by `api-log.conf.yaml`. Its `default` formatter is
  `%(asctime)s.%(msecs)03dZ %(levelname)-8s %(message)s`; the `access` formatter
  adds `%(client_addr)s "%(request_line)s" %(status_code)s`
  (`api-log.conf.yaml:3-9`).
- **`access.log` is JSON; the instrukt-ai diagnostic files are plain-text logfmt.**
  `access.log` remains the CrowdSec feed and is pretty-printed by
  `bin/format-logs.py` when tailed manually.
- **Container logs are ephemeral.** Removing a container discards its Docker logs;
  only the `logs/` files and the instrukt-ai diagnostic folder survive container
  lifecycle. Durable analysis must use the file-based logs.

## Primary flows

**Viewing diagnostic logs (`instrukt-ai-logs itsup [--include <source>] [--since W]
[--grep RE]`):** the shipped viewer resolves the files under
`instrukt-ai/itsup/` and follows them (rotation-aware). `--include monitor`
narrows to `monitor.log`; with no filter it merges every source in the folder.

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

**Monitor logging:** `bin/monitor.py` calls
`configure_logging("itsup", source="monitor")` (bridging `LOG_LEVEL` →
`ITSUP_LOG_LEVEL`), so the monitor's diagnostics land in
`instrukt-ai/itsup/monitor.log`; its `[<ts>] Started` watermark and operator
banners are unaffected.

## Failure modes

- **Unwritable diagnostic log dir/file.** `configure_logging` treats logging as an
  essential subsystem and raises at startup if the log dir/file cannot be written —
  there is no degraded or console-fallback mode. A supervised process that cannot
  open its file fails fast rather than starting blind.
- **Missing watermark.** If `logs/monitor.log` is absent or has no `[<ts>]` marker,
  `monitor/core.py:_get_last_processed_timestamp` returns `None` and the monitor
  reprocesses the docker-log window from scratch — correct, just less efficient.
- **Malformed access-log line.** `bin/format-logs.py` catches
  `json.JSONDecodeError` and passes the raw line through (`:111-113`); a parse
  exception inside a valid JSON object yields a `[PARSE ERROR: ...]` prefix rather
  than crashing the stream (`:96-98`).
- **Container removal.** Container (Docker json-file) logs are lost when the
  container is removed; only the `logs/` files and the instrukt-ai diagnostic
  folder persist.
