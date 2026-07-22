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
- **`uvicorn.error` declares no handler but does not reach the root logger.**
  It sets no `propagate: False` of its own, so its records walk up to the
  parent `uvicorn` logger — which *does* carry the `default` stderr handler and
  *does* set `propagate: False`. The record is emitted there and propagation
  stops. A handler an application attaches to root therefore receives **zero**
  `uvicorn.error` records, with uvicorn's formatter rather than the
  application's.

### `log_config` and `log_level` overrides

Passing `log_config=<path>` replaces this default wholesale; passing
`log_level=` overrides the level uvicorn applies to its own loggers. Omitting
both yields the table above.

A custom `log_config` whose **named** loggers do not match `uvicorn`,
`uvicorn.error` and `uvicorn.access` configures nothing for uvicorn *by name*:
handlers attached to those unmatched names are never selected for uvicorn's
records. This failure is silent — the config loads without error and the
handler's file is created and stays empty.

A handler the same config attaches to **`root`** is a different case and is
**not** dead: every record that propagates to root reaches it, including
`uvicorn.error`'s (which sets no `propagate: False`). So a config can be
half-live — its root handler receiving records while a same-config named handler
never fires.

itsUP's own `api-log.conf.yaml` is exactly that shape, and it is the reason the
two files behave differently today:

| Handler | Attached to | Selected? |
|---|---|---|
| `default` → `logs/api.log` | `default` logger **and `root`** | **Yes**, via `root` — receives propagated records |
| `access` → `logs/access.log` | `access` logger only | **No** — uvicorn's access logger is `uvicorn.access`, which this config never names |

Reading "the handlers it declares are never selected" as covering both is wrong:
`logs/api.log` has content, and the record that never arrives is uvicorn's
*access* record.

## Known caveats

- **Version-pinned observation.** The absence of a `root` key is a property of
  the installed version's `LOGGING_CONFIG`, verified by reading it. Re-verify
  after a uvicorn major upgrade before relying on root-handler survival.
- **A handler attached only to an unmatched named logger is a silent no-op**:
  its file is created and stays empty, which reads on inspection exactly like a
  logging path that works. This does **not** extend to a handler the same config
  attaches to `root` — see the selection rules above; a config can be half-live,
  and inferring "the whole config is dead" from one empty file is the mistake
  the section above exists to prevent.

## Sources

- https://www.uvicorn.org/settings/
- https://github.com/encode/uvicorn/blob/master/uvicorn/config.py
