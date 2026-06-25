---
description: 'How itsUP backs up and restores stateful stores: the per-project backup.yml
  adapter registry, the dump/restore adapter contract, in-tarball dump placement so
  the single monolithic archive ships everything, derived live-tar exclusion, proxy-state
  capture, and the guarded restore dispatcher.'
visibility: internal
---

# Backup & Restore — Design

## Purpose

itsUP backs up host state by tarring `upstream/` (and `proxy/`) and uploading a
single timestamped archive to S3 with keep-10 rotation (`bin/backup.py`). That
archive is crash-inconsistent for live stores — a database's data directory
copied while the engine is writing cannot be safely restored — and there is no
restore path at all.

This design closes both gaps with one mechanism: a **per-project adapter** that
produces a *consistent logical dump next to its data in the archive tree*, so the
existing monolithic tar sweeps the dump up and ships it unchanged. Adapters never
touch S3 — the mother script owns shipping. The same adapter supplies the inverse
`restore`, loading the dump back **into the running instance**. A store that
declares an adapter is automatically excluded from the live-tar at its declared
paths, so its torn data directory is never archived while its consistent dump is.

The framework is the deliverable; Postgres is the first adapter that proves the
round trip. New stateful stores plug in by authoring an adapter pair plus a
`backup.yml` — with no change to the framework.

## Inputs/Outputs

**Inputs**

- `projects/<name>/backup.yml` — the per-project registry entry. Travels with the
  project (not the infra config), decoupled from the ephemeral `upstream/`:
  - `adapter: <name>` — the adapter that backs this project (resolves to
    `bin/backup-adapters/<name>.sh`).
  - `exclude: [<path>...]` — live-state paths under the project's archive dir to
    keep out of the monolithic tar (e.g. `data`), so the torn live directory is
    skipped while the adapter dump is included.
- The **running container** for an adapter-backed project, reached via the
  existing compose-exec pattern with `get_env_with_secrets(project)` from
  `lib.data`.
- `upstream/<name>/` — the project's archive dir (where `./data` materializes;
  see `project/design/deployment-orchestration`), and the dump's destination.
- `proxy/` — Traefik config + `acme.json` certificates, added to the monolithic
  archive.
- S3 credentials (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_HOST`,
  `AWS_S3_REGION`, `AWS_S3_BUCKET`) loaded from the infra secrets via
  `load_secrets()` — the existing boto3 access pattern, reused unchanged.

**Outputs**

- One timestamped archive `itsup.tar.gz.<timestamp>` in the S3 bucket, retained
  at the last 10 versions. The archive now contains, per adapter-backed project,
  the consistent dump under `upstream/<name>/_backup/` and excludes that
  project's declared live paths; it also contains `proxy/` state.
- On restore, a recovered **running instance** for adapter-backed projects, and a
  filesystem extract for non-adapter projects.

## Invariants

- **Adapters never touch S3.** `dump` writes a local file; `restore` reads a local
  file. The mother script (`bin/backup.py`) is the sole owner of archiving and
  upload, and `bin/restore.py` is the sole owner of download and extraction. The
  existing rotate+upload path is reused unchanged — never duplicated per adapter.
- **One archive, one retention.** Dumps ride inside the single monolithic
  `itsup.tar.gz.<timestamp>`; retention is the existing keep-10 rotation on that
  archive. There is no separate per-adapter S3 object and no PITR.
- **Derived exclusion.** The live-tar exclusion set is derived from the presence
  of `projects/<name>/backup.yml` and its `exclude` paths — there is no separately
  maintained exclude list. A project with an adapter is never both adapter-dumped
  and live-tarred at the same paths.
- **Database restore is logical, into the running instance.** An adapter restore
  loads the dump into the live engine; it never drops a filesystem snapshot into a
  data directory. This distinction is the correctness fix.
- **Restore is guarded.** Any restore that would overwrite existing data prompts
  for confirmation first. Restore is a bare dispatcher (`bin/restore.py`), not an
  `itsup` subcommand.
- **Dump-before-tar ordering.** The mother script runs every adapter `dump` to
  completion before it begins the tar, so the archive captures the just-written
  consistent dumps.

## Primary flows

### Backup

```mermaid
flowchart TD
    A[bin/backup.py] --> B{for each projects/&lt;name&gt;/backup.yml}
    B -->|has adapter| C[run bin/backup-adapters/&lt;name&gt;.sh dump upstream/&lt;name&gt;]
    C --> D[consistent dump written to upstream/&lt;name&gt;/_backup/]
    B -->|done| E[tar upstream/ + proxy/]
    E --> F[skip paths declared in each backup.yml exclude]
    F --> G[itsup.tar.gz.&lt;ts&gt;]
    G --> H[keep-10 rotate + upload to S3 — existing path, unchanged]
```

### Restore

```mermaid
flowchart TD
    A[bin/restore.py &lt;project&gt; --from &lt;s3-key&gt;] --> B[download archive generation from S3]
    B --> C[extract]
    C --> D{project has backup.yml adapter?}
    D -->|yes| E[confirm overwrite guard]
    E --> F[run adapter restore upstream/&lt;name&gt; into the running instance]
    D -->|no| G[confirm overwrite guard]
    G --> H[filesystem extract into upstream/&lt;name&gt;]
```

### Adapter contract

An adapter is `bin/backup-adapters/<name>.sh` exposing two verbs, each receiving
the project's archive dir:

- `dump <project-upstream-dir>` — write a consistent dump under
  `<project-upstream-dir>/_backup/`. No S3.
- `restore <project-upstream-dir>` — load that dump into the running instance. No
  S3.

The **Postgres** adapter: `dump` runs `pg_dumpall --globals-only` (roles) plus a
per-database `pg_dump -Fc`, executed through the compose-exec pattern, into
`upstream/postgres/_backup/`. `restore` establishes roles/globals first, then
`pg_restore`/`psql` each database into the running instance. `projects/postgres/`
declares `adapter: postgres` and `exclude: [data]`.

## Failure modes

- **Instance unreachable at dump/restore time.** Adapter operations run against
  the live container; if it is down the operation fails loudly rather than
  producing a silent partial dump. The dump step surfaces the error to the mother
  script.
- **Restore order dependency.** A per-database restore before roles/globals exist
  fails on missing roles. The Postgres adapter sequences globals first; this
  ordering is part of the adapter contract for any role-bearing store.
- **Destructive overwrite.** Restore overwriting a running service's data is
  guarded by an explicit confirmation before any write.
- **Exclusion derivation error.** If derivation wrongly includes an
  adapter-managed live path, the archive carries both a torn directory and the
  dump (wasteful, and the torn copy is misleading); if it wrongly drops a
  non-adapter project, that project is lost. Derivation is driven solely by the
  presence and `exclude` paths of `backup.yml`.
- **Double compression.** A `pg_dump -Fc` (already compressed) re-compressed by the
  gzip tar yields little extra and costs CPU; it is harmless and accepted, not
  specially cased.

## See Also

- docs/project/design/deployment-orchestration.md
- docs/project/design/network-segmentation.md
