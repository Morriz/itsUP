---
description: 'How itsUP produces, formats, and consumes logs — the file-based logs/ directory written by Traefik and the Python services, the TTY-aware vs structured formatting split, the access.log → CrowdSec feed, ephemeral container logs, and the itsup logs viewer.'
---

# Logging — Design

## Purpose

itsUP runs a mix of containerized upstream services and non-containerized itsUP
code (API, monitor, CLI, artifact generation). It needs a single place to read
operational logs across both worlds, a machine-parseable access log that
CrowdSec can analyze for threats, and human-readable output when an operator
tails logs interactively.

The design splits logging by producer: Traefik and the Python services write
durable files into a shared `logs/` directory; every Docker container also emits
to Docker's own json-file driver. The `logs/` files are the durable,
operator-facing surface; container logs are ephemeral debugging output.

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
- `logs/monitor.log` — security monitor log. Path is
  `monitor/constants.py:17` (`LOG_FILE = .../logs/monitor.log`); the monitor
  entrypoint calls `setup_logging(log_file=LOG_FILE)` at `bin/monitor.py:208`.

<!-- planned:adopt-logger-cli -->
**CLI diagnostic log (`instrukt_ai_logging`, host-side):**

- `$XDG_STATE_HOME/instrukt-ai/itsup/itsup.log` (fallback
  `~/.local/state/instrukt-ai/itsup/itsup.log`) — the `itsup` CLI's diagnostic
  record, plain-text logfmt. Written by
  `instrukt_ai_logging.configure_logging("itsup")` (`itsup/cli.py`), which
  installs a file-only handler with no console output. It lives outside the
  shared `logs/` directory and is not part of the CrowdSec feed.
<!-- /planned:adopt-logger-cli -->

**Container logs (ephemeral):** every Docker container also writes to Docker's
default json-file driver. Read via `docker logs` / `docker compose logs`. These
are not part of the `logs/` directory contract.

**Consumers:**

- **CrowdSec** reads `logs/access.log` (mounted into its container at
  `/var/log/traefik/access.log`) as a log acquisition source
  (`crowdsec/acquis.yml:8-11`, `labels.type: traefik`). This is the threat-
  detection feed.
- **`itsup logs`** (`commands/logs.py`) tails files from `logs/` with optional
  JSON formatting.
- **Operators** via direct `tail`/`zcat`.

## Invariants

<!-- planned:adopt-logger-cli -->
- **The `itsup` CLI splits emission into two channels by audience.** Human-facing
  output — everything a person reads on screen — is emitted with `click` in the
  command/entry layer (`commands/`), which keeps color and the `✓`/`⚠`/`✗` icons
  and auto-strips them when stdout is not a TTY. A single shared helper in
  `commands/common.py` (`ok`/`warn`/`fail`/`step`, via `click.secho`) renders
  them; no command carries its own ANSI table. Diagnostic/audit output is emitted
  with `instrukt_ai_logging` (`get_logger("itsup.<module>")`), plain-text logfmt,
  to the CLI diagnostic file only — never to the terminal. `lib/` never writes to
  the terminal: library functions return data or raise, and the calling command
  echoes any human-facing result. `itsup/cli.py` calls `configure_logging("itsup")`
  once; `-v`/`-vv` set `ITSUP_LOG_LEVEL` to `DEBUG`/`TRACE` before that call, and
  loggers are acquired under the `itsup.` prefix so the app log level governs them.
<!-- /planned:adopt-logger-cli -->
- **Two formatters, selected by destination, not by service.**
  `lib.logging_config.setup_logging` (`lib/logging_config.py:110-149`) detects
  `sys.stdout.isatty()`. TTY → clean colored output with symbols (`✓ ⚠ ✗`,
  `%(message)s`). Non-TTY (pipe/file/daemon) → structured
  `%(asctime)s %(levelname)s > %(custom_pathname)s:%(lineno)d: %(message)s`
  (`lib/logging_config.py:79`). File handlers always use the structured
  (non-TTY) format regardless of the console mode
  (`lib/logging_config.py:142-145`).
- **The API/access log format is uvicorn's, not `lib.logging_config`'s.** The
  API process is configured entirely by `api-log.conf.yaml`. Its `default`
  formatter is `%(asctime)s.%(msecs)03dZ %(levelname)-8s %(message)s`; the
  `access` formatter adds `%(client_addr)s "%(request_line)s" %(status_code)s`
  (`api-log.conf.yaml:3-9`).
<!-- planned-change:adopt-logger-cli -->
  The monitor and other CLI entrypoints use
  `lib.logging_config` instead.
<!-- change:adopt-logger-cli -->
  The monitor and the remaining daemon entrypoints (backup, migration, artifact
  generation) use `lib.logging_config`; the `itsup` CLI configures diagnostics
  through `instrukt_ai_logging` instead (see the two-channel invariant above).
<!-- /planned-change:adopt-logger-cli -->

- **`access.log` is JSON, every other file is plain text.** `commands/logs.py:16`
  hard-codes `JSON_LOGS = {"access"}`; only that file is piped through the
  formatter.
- **Container logs are ephemeral.** Removing a container discards its Docker logs;
  only `logs/*.log` survives container lifecycle. Durable analysis must use the
  file-based logs.

## Primary flows

**Viewing logs (`itsup logs [names...] [-n N]`, `commands/logs.py`):**

1. With no names, defaults to every `*.log` in `logs/` (rotated `.log.1`/`.log.2`
   excluded, `commands/logs.py:27`).
2. Validates each requested name resolves to `logs/<name>.log`.
3. If any requested log is in `JSON_LOGS` (`access`), the pipeline is
   `tail -n N -F <files> | bin/format-logs.py`; otherwise a bare `tail -n N -F`.
   `-q` is added when more than one file is tailed to suppress filename headers
   (`commands/logs.py:88-91,120-124`).

**Access-log formatting (`bin/format-logs.py`):** reads JSON lines from stdin and
emits a flat line: `TIME LEVEL CLIENT_IP "METHOD HOST/PATH" → SERVICE STATUS
DURATION [overhead] SIZE [retries] [TLS]` (`bin/format-logs.py:24-94`). Duration
is ns→ms (`Duration` field ÷ 1e6, `bin/format-logs.py:19-21,52-56`), the
`@docker` suffix is stripped
from `ServiceName`, overhead is shown only when > 0.5ms, and non-JSON lines pass
through unchanged (`bin/format-logs.py:111-113`).

**Threat detection:** Traefik appends each request to `logs/access.log` → the
CrowdSec acquisition source (`crowdsec/acquis.yml`) parses it under the `traefik`
label for detection.

**Monitor logging:** `bin/monitor.py:208` calls `setup_logging(log_file=LOG_FILE)`
so monitor output goes to both the console (TTY-aware) and `logs/monitor.log`
(structured).

## Failure modes

- **Empty `logs/` directory.** `commands/logs.py:65-67` exits non-zero with
  "No log files found in logs/" when `get_available_logs()` returns nothing
  (directory missing or contains no `*.log`).
- **Unknown log name.** Requesting a name with no matching `logs/<name>.log`
  prints the available list and exits non-zero (`commands/logs.py:71-75`).
- **Malformed access-log line.** `bin/format-logs.py` catches
  `json.JSONDecodeError` and passes the raw line through (`:111-113`); a parse
  exception inside a valid JSON object yields a `[PARSE ERROR: ...]` prefix rather
  than crashing the stream (`:96-98`).
- **Container removal.** Container (Docker json-file) logs are lost when the
  container is removed; only the `logs/` files persist.
