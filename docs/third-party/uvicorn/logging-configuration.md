---
description: uvicorn's default LOGGING_CONFIG as installed for itsUP — it configures only the uvicorn* loggers, declares no root key and does not disable existing loggers, so a handler attached to the root logger before uvicorn.run survives; and its default handler writes to stderr while the access handler writes to stdout.
---

# uvicorn — Logging Configuration

## What it is

itsUP's API runs under uvicorn. Today it passes an explicit
`log_config="api-log.conf.yaml"`, which puts a `logging.FileHandler` on the root
logger; `api/main.py` attaches no handler of its own. Any change that drops that
config and instead relies on a handler attached to the **root logger** before
`uvicorn.run(...)` — the usual shape for a process whose stdout a supervisor
captures — depends on exactly what uvicorn's own `dictConfig` touches, and on
which stream each uvicorn handler writes to. Guessing either yields an API that
loses every application record, or duplicates them. This entry records what the
installed default actually does.

## Canonical fields

Verified against the installed version rather than the published docs, by
reading `uvicorn.config.LOGGING_CONFIG` directly.

**Installed version at time of verification: uvicorn 0.50.2.**

### The default config touches only the `uvicorn*` loggers

Top-level keys: `version`, `disable_existing_loggers`, `formatters`, `handlers`,
`loggers`.

- **There is no `root` key.** `logging.config.dictConfig` therefore does not
  reconfigure the root logger, and handlers already attached to root are left in
  place.
- **`disable_existing_loggers` is `False`.** Loggers created before
  `uvicorn.run` — such as the application's `itsup.*` hierarchy — are not
  disabled.

The consequence: configuring a root stdout handler **before** calling
`uvicorn.run` is sufficient and needs no re-application afterwards. There is no
branch to design for.

### Configured loggers and their streams

| Logger | Level | Handlers | `propagate` |
| --- | --- | --- | --- |
| `uvicorn` | INFO | `default` | `False` |
| `uvicorn.error` | INFO | *(none)* | *(default: true)* |
| `uvicorn.access` | INFO | `access` | `False` |

| Handler | Class | Stream |
| --- | --- | --- |
| `default` | `logging.StreamHandler` | `ext://sys.stderr` |
| `access` | `logging.StreamHandler` | `ext://sys.stdout` |

Two details that are easy to state wrongly:

- **Server records go to stderr, access records go to stdout.** Not both to
  stdout. Under a supervisor that captures both streams this is immaterial to
  where records land, but it is wrong to document uvicorn as "logging to
  stdout".
- **`uvicorn.error` declares no handler and does not set `propagate: False`**,
  so its records propagate to the root logger and are emitted by whatever
  handler the application attached there — with the application's formatter, not
  uvicorn's.

### `log_config` and `log_level` overrides

Passing `log_config=<path>` replaces this default wholesale; passing
`log_level=` overrides the level uvicorn applies to its own loggers. Omitting
both yields the table above.

A custom `log_config` whose logger names do not match `uvicorn`,
`uvicorn.error` and `uvicorn.access` silently configures nothing for uvicorn:
the handlers it declares are never selected, and uvicorn's records fall through
to whatever the root logger does. This failure is silent — the config loads
without error.

## Known caveats

- **Version-pinned observation.** The absence of a `root` key is a property of
  the installed version's `LOGGING_CONFIG`, verified by reading it. Re-verify
  after a uvicorn major upgrade before relying on root-handler survival.
- **A `log_config` naming non-uvicorn loggers is a silent no-op for uvicorn**,
  and any handler it points at a file is created and left empty — which reads,
  on inspection, exactly like a logging path that works.

## Sources

- https://www.uvicorn.org/settings/
- https://github.com/encode/uvicorn/blob/master/uvicorn/config.py
