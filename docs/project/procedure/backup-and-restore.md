---
description: Back up itsUP runtime state (upstream/) to S3 and restore config + state after host, data, or repo loss.
---

# Backup and Restore — Procedure

## Goal

Protect an itsUP container host against data loss along two independent axes:

- **Configuration** lives in git. `projects/` (compose + ingress + traefik overrides) and `secrets/` (SOPS-encrypted `*.enc.txt`) are restored by re-cloning their remotes via `itsup init`.
- **Runtime state** lives under `upstream/` (the deployed compose trees and their bind-mounted container volumes). `bin/backup.py` tars `upstream/` and uploads it to an S3-compatible bucket (`bin/backup.py:23`, `bin/backup.py:61-68`).

Restore means: re-clone the repos, decrypt secrets, pull the latest `upstream/` archive from S3, extract it, and `itsup apply`.

## Preconditions

- **Git remotes for `projects/` and `secrets/`.** `itsup init` clones both from URLs you supply and checks out `main` (`commands/init.py:60-76`, `commands/init.py:107-148`). Without remotes, configuration is unrecoverable from git.
- **AWS / S3-compatible credentials in itsUP secrets.** `bin/backup.py` reads five keys from `secrets/itsup.{enc.txt|txt}` and aborts if any are missing (`bin/backup.py:73-85`): `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_HOST`, `AWS_S3_REGION`, `AWS_S3_BUCKET`. `AWS_S3_HOST` is a full endpoint host (any non-`http(s)://` value is prefixed with `https://`), so non-AWS S3-compatible providers work (`bin/backup.py:96-99`). The client signs with `s3v4` (`bin/backup.py:114`).
- **SOPS + age key for encrypted secrets.** `itsup decrypt` requires the `sops` binary on PATH (`commands/decrypt.py:44-51`). Decryption (and reading `secrets/itsup.enc.txt` during backup) needs the age private key at `~/.config/sops/age/keys.txt`; the nightly backup service sets `HOME=/home/{{USER}}` precisely so root finds it (`samples/systemd/itsup-backup.service:13-18`).
- **The `upstream/` directory must exist.** `bin/backup.py` exits with an error if `./upstream` is absent (`bin/backup.py:23-26`).

## Steps

### Manual backup of runtime state

Run from the repo root on the container host:

```bash
.venv/bin/python bin/backup.py
```

It loads `backup.exclude` (a list of top-level folder names to skip) from `projects/itsup.yml`, defaulting to `[]` when absent (`bin/backup.py:29-31`); tars every other entry under `upstream/` into a local `itsup.tar.gz` (`bin/backup.py:20`, `bin/backup.py:61-68`); uploads it; and deletes the local tarball afterward (`bin/backup.py:170-173`). Files that vanish mid-walk (e.g. redis snapshot rename) are skipped per-entry rather than aborting the run (`bin/backup.py:36-57`).

Configuration is backed up separately by committing and pushing the git repos:

```bash
itsup commit "<message>"   # commits + pushes projects/ and secrets/
```

### Automated nightly backup

`make install` enables `itsup-backup.timer`, which fires `itsup-backup.service` at 05:00 daily with `Persistent=true` so a missed run executes at next boot (`samples/systemd/itsup-backup.timer:5-7`, `bin/install-bringup.sh:154-159`). The service runs as root (to read root-owned container volumes), sources `env.sh`, and invokes `.venv/bin/python bin/backup.py` (`samples/systemd/itsup-backup.service:6-20`).

### Restore

1. **Re-clone and initialize configuration.** From a fresh repo checkout on the host:
   ```bash
   itsup init
   ```
   This clones `projects/` and `secrets/` from their remotes and copies any missing sample config (`commands/init.py:188-255`).
2. **Decrypt secrets** (requires SOPS + age key):
   ```bash
   itsup decrypt          # all secrets/*.enc.txt
   itsup decrypt itsup    # a single file
   ```
   (`commands/decrypt.py:60-86`)
3. **Restore runtime state from S3.** Download the most recent `itsup.tar.gz.<timestamp>` object from the bucket and extract it into the repo root so it recreates `upstream/`:
   ```bash
   # using the same endpoint/bucket as in secrets/itsup.txt
   tar -xzf itsup.tar.gz.<timestamp>
   ```
   The archive's members are paths relative to `upstream/` (arcname is each item's basename, `bin/backup.py:64-68`), so extract from the directory that contains `upstream/`.
4. **Deploy:**
   ```bash
   itsup apply            # all projects, or: itsup apply <project>
   ```

## Outputs

- **S3 objects** named `itsup.tar.gz.<YYYYMMDDHHMMSS>` at the bucket root — there is no key prefix and no `latest` alias (`bin/backup.py:130-131`, `bin/backup.py:144-146`). Rotation keeps the 10 newest timestamped objects and deletes older ones (`bin/backup.py:134-141`).
- **Each archive** is a gzip tarball of `upstream/`'s contents minus excluded folders (`bin/backup.py:61-68`).
- **After restore:** decrypted `secrets/*.txt`, a populated `upstream/` tree, and a running stack once `itsup apply` completes.

## Recovery

- **Host hardware loss.** Provision a new host, `make install`, clone the itsUP repo, then run the full Restore (init → decrypt → S3 extract → apply). Configuration comes from git; runtime state from the latest S3 archive.
- **Accidental config/secret deletion.** Restore from git rather than S3 — `git checkout` the affected paths under `projects/` (and the `*.enc.txt` under `secrets/`), `itsup decrypt`, then `itsup apply <project>`. The S3 archive holds only `upstream/`, never the source config.
- **Volume / `upstream/` corruption.** Extract the most recent `itsup.tar.gz.<timestamp>` over the repo root and `itsup apply`. Only data captured at the last backup is recoverable; anything written since is lost (worst case ~24h with the nightly timer).
- **Repo loss with remotes intact.** Re-clone via `itsup init`; nothing else is needed for configuration. If a remote is also gone, `upstream/` from S3 contains generated compose files but not the source `projects/`/`secrets/` definitions — reconstruct those by hand.
- **Lost age key.** Without `~/.config/sops/age/keys.txt`, `*.enc.txt` cannot be decrypted and `bin/backup.py` cannot read AWS credentials from `secrets/itsup.enc.txt`. Keep the age key backed up independently of this repo.

## See Also

- docs/project/design/network-segmentation.md — how upstream/ compose trees are generated.
