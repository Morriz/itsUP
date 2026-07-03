---
description: Back up itsUP runtime state (upstream/ + proxy/) to S3 with per-project adapter dumps, and restore config + state — including logical database restore into the running instance — after host, data, or repo loss.
visibility: 'internal'
---

# Backup and Restore — Procedure

## Goal

Protect an itsUP container host against data loss along two independent axes:

- **Configuration** lives in git. `projects/` (compose + ingress + traefik overrides + per-project `backup.yml`) and `secrets/` (SOPS-encrypted `*.enc.txt`) are restored by re-cloning their remotes via `itsup init`.
- **Runtime state** lives under `upstream/` (the deployed compose trees and their bind-mounted container volumes) and `proxy/` (Traefik config + `acme.json` certificates). `bin/backup.py` tars both and uploads a single monolithic archive to an S3-compatible bucket.

For a stateful store, a crash-consistent copy of a live data directory is not safely restorable. A project therefore declares a per-project **adapter** in `projects/<name>/backup.yml`; the adapter writes a consistent logical dump into the archive, and its live data directory is excluded from the tar. Restore loads that dump back **into the running instance** rather than dropping a filesystem snapshot. The framework is general; Postgres is the first adapter. The full contract lives in `project/design/backup-restore`.

Restore means: re-clone the repos, decrypt secrets, then run `bin/restore.py` to pull an archive generation from S3 and route it to each project's adapter restore (or a filesystem extract), guarded by a confirmation prompt.

## Preconditions

- **Git remotes for `projects/` and `secrets/`.** `itsup init` clones both from URLs you supply and checks out `main`. Without remotes, configuration is unrecoverable from git.
- **AWS / S3-compatible credentials in itsUP secrets.** `bin/backup.py` and `bin/restore.py` build their S3 client via the shared `build_s3_client` helper, which reads five keys from `secrets/itsup.{enc.txt|txt}` and aborts if any are missing: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_HOST`, `AWS_S3_REGION`, `AWS_S3_BUCKET`. `AWS_S3_HOST` is a full endpoint host (any non-`http(s)://` value is prefixed with `https://`), so non-AWS S3-compatible providers work. The client signs with `s3v4`.
- **SOPS + age key for encrypted secrets.** `itsup decrypt` requires the `sops` binary on PATH. Decryption (and reading `secrets/itsup.enc.txt` during backup) needs the age private key at `~/.config/sops/age/keys.txt`; the nightly backup service sets `HOME=/home/{{USER}}` precisely so root finds it (`samples/systemd/itsup-backup.service`).
- **The `upstream/` directory must exist.** `bin/backup.py` exits with an error if `./upstream` is absent.
- **A reachable running instance for adapter operations.** An adapter dump or restore runs against the live container via the compose-exec pattern. For backup, an unreachable instance is skipped and the run is flagged partial; for restore, an adapter-backed project requires its instance to be up.

## Steps

### Per-project backup registry

Each project that needs special backup handling carries `projects/<name>/backup.yml` (loaded by `load_project_backup_config`):

- `adapter: <name>` — optional. When set, the named adapter produces a consistent logical dump under `upstream/<name>/_backup/` before the tar. The adapter script is resolved project-local first (`projects/<name>/backup-adapter.sh`), then from the shared set (`bin/backup-adapters/<name>.sh`).
- `exclude: [<path>...]` — live-state paths under `upstream/<name>/` kept out of the tar (e.g. `data`). An ephemeral store (e.g. redis) sets only `exclude` with no `adapter`, dropping its volatile data from the archive without producing a dump.

The live-tar exclusion is derived solely from these files — there is no separately maintained exclusion list, and no `backup.exclude` field in `projects/itsup.yml`.

### Manual backup of runtime state

Run from the repo root on the container host:

```bash
.venv/bin/python bin/backup.py
```

It discovers every `upstream/<name>` carrying a `backup.yml`; runs the adapter dumps concurrently before the tar; derives the exclusion set from each project's `exclude` paths; tars `upstream/` (minus excluded paths) plus `proxy/` into a local `itsup.tar.gz`; uploads it; and deletes the local tarball afterward. Files that vanish mid-walk (e.g. a redis snapshot rename) are skipped per-entry rather than aborting the run.

A single adapter dump that fails (container down, exec error) is logged and that project is skipped — the run still archives and uploads every healthy project plus `proxy/` state, then exits non-zero with a `PARTIAL BACKUP` summary naming each skipped project. A degraded run never reports success.

Configuration is backed up separately by committing and pushing the git repos:

```bash
itsup commit "<message>"   # commits + pushes projects/ and secrets/
```

### Automated nightly backup

`make install` enables `itsup-backup.timer`, which fires `itsup-backup.service` at 05:00 daily with `Persistent=true` so a missed run executes at next boot. The service runs as root (to read root-owned container volumes) with `HOME` pinned to the itsUP user so SOPS finds the age key, and invokes the absolute `.venv/bin/python bin/backup.py` directly.

### Restore

`bin/restore.py` is a bare dispatcher — restore is destructive, so it ships outside the `itsup` subcommands and guards every run.

1. **Re-clone and initialize configuration.** From a fresh repo checkout on the host:
   ```bash
   itsup init
   ```
   This clones `projects/` and `secrets/` from their remotes and copies any missing sample config.
2. **Decrypt secrets** (requires SOPS + age key):
   ```bash
   itsup decrypt          # all secrets/*.enc.txt
   itsup decrypt itsup    # a single file
   ```
3. **Restore runtime state from S3.** Choose a target — a project name, `all`, or `proxy`:
   ```bash
   .venv/bin/python bin/restore.py all            # whole stack + proxy
   .venv/bin/python bin/restore.py postgres       # one project
   .venv/bin/python bin/restore.py proxy          # proxy config + certs
   .venv/bin/python bin/restore.py all --list     # list available generations
   .venv/bin/python bin/restore.py all --from itsup.tar.gz.<timestamp>
   ```
   Restore downloads the chosen generation (the latest when `--from` is omitted), extracts it, and routes each target: an adapter-backed project loads its dump into the running instance via the adapter's `restore` verb; a non-adapter project is a filesystem extract into `upstream/<name>`; `proxy` extracts the archived `proxy/` state. Every run prompts for confirmation before any write; pass `-y`/`--yes` for non-interactive automation.
4. **Deploy:**
   ```bash
   itsup apply            # all projects, or: itsup apply <project>
   ```

## Outputs

- **S3 objects** named `itsup.tar.gz.<YYYYMMDDHHMMSS>` at the bucket root — there is no key prefix and no `latest` alias. Rotation keeps the 10 newest timestamped objects and deletes older ones.
- **Each archive** is a gzip tarball containing `upstream/<name>/...` (minus excluded paths, with each adapter's `_backup/` dump included) and `proxy/...` state.
- **After restore:** decrypted `secrets/*.txt`, restored `upstream/` trees and `proxy/` state, adapter-backed databases reloaded into their running instances, and a running stack once `itsup apply` completes.

## Recovery

- **Host hardware loss.** Provision a new host, `make install`, clone the itsUP repo, then run the full Restore (init → decrypt → `bin/restore.py all` → apply). Configuration comes from git; runtime state and proxy certificates from the latest S3 archive.
- **Accidental config/secret deletion.** Restore from git rather than S3 — `git checkout` the affected paths under `projects/` (and the `*.enc.txt` under `secrets/`), `itsup decrypt`, then `itsup apply <project>`. The S3 archive holds runtime state, never the source config.
- **Database corruption or loss.** Run `bin/restore.py <project>` for the adapter-backed store; the adapter recreates roles/globals and reloads each database into the running instance. Only data captured at the last backup is recoverable; anything written since is lost (worst case ~24h with the nightly timer).
- **Volume / `upstream/` corruption (non-adapter project).** Run `bin/restore.py <project>` for a filesystem extract, then `itsup apply`.
- **Proxy certificate / config loss.** Run `bin/restore.py proxy` to recover `proxy/` config and `acme.json`.
- **Repo loss with remotes intact.** Re-clone via `itsup init`; nothing else is needed for configuration. If a remote is also gone, the S3 archive contains generated compose files and runtime state but not the source `projects/`/`secrets/` definitions — reconstruct those by hand.
- **Lost age key.** Without `~/.config/sops/age/keys.txt`, `*.enc.txt` cannot be decrypted and the backup cannot read AWS credentials from `secrets/itsup.enc.txt`. Keep the age key backed up independently of this repo.

## See Also

- docs/project/design/backup-restore.md — the adapter framework, registry, and restore-dispatch contract.
- docs/project/design/network-segmentation.md — how upstream/ compose trees are generated.
