---
description: Acceptance scenario for bin/backup.py's S3 upload integrity — the archive
  is published to its final generation name only after a staged upload is verified
  complete, so an interrupted or truncated upload never leaves an object under the
  final itsup.tar.gz.<timestamp> name; retention keeps only validated generations
  and prunes after promotion, and bin/restore.py offers only validated generations.
---

# Backup Upload Integrity — Spec

## Required reads

- @docs/project/spec/runtime-operations.md

## What it is

`bin/backup.py` uploads the `itsup.tar.gz` archive to S3 under a timestamped
generation name `itsup.tar.gz.<timestamp>` and retains the newest ten
generations; `bin/restore.py` restores the newest generation by default. A
generation is only ever published under that final name once its upload is proven
complete.

Publication is atomic through a staging boundary. The archive is first uploaded
to a **staging key** held outside the `itsup.tar.gz.` generation prefix. Its
stored byte length is then compared to the local archive's, and only on a match is
the staged object promoted — by a server-side copy — to its final
`itsup.tar.gz.<timestamp>` name and marked validated (a small companion marker
object, also outside the generation prefix). An interrupted, truncated, or
otherwise incomplete upload never passes verification, so it is never copied to the
final name — no object is ever published under `itsup.tar.gz.<timestamp>` for a
failed run; the staging object is cleaned up.

Both consumers gate on validation, not on recency or name alone:

- **Retention** keeps the newest ten **validated** generations, evicting
  unvalidated objects (a legacy generation from before this contract, or a stray)
  before validated ones, so an object that never passed verification can never
  displace one that did. Pruning runs only after the current generation is
  promoted, so a failed run never deletes a validated generation.
- **Restore** offers only validated generations by default; an explicit
  operator-named archive key is still restorable for recovering a legacy
  generation.

The business value is that the disaster-recovery substrate cannot be silently
poisoned: a partial upload never appears under a real generation name, recency
cannot preserve a corrupt object at the expense of a good one, and restore cannot
default to an unverified archive — the failure that would otherwise surface only
at restore time, when it can least be tolerated.

### Use cases

The scenario below is bound by exactly one functional test that drives the real
upload, retention, and restore paths with the S3 service faked at the process
boundary, simulating a transfer that lands fewer bytes than the archive holds and
folding in the success, retention-priority, and restore controls that prove the
whole contract.

#### UC-BUI1: An incomplete upload never publishes under the final generation name

```gherkin
Given validated generations already exist in the bucket
And bin/backup.py uploads a new archive to S3 but the transfer lands only part of its bytes
When the upload step completes
Then no object exists under the final itsup.tar.gz.<timestamp> name for that run
And every pre-existing validated generation is still present
And a subsequent complete upload does publish and validate exactly one new generation
And retention evicts an unvalidated object before any validated generation
And bin/restore.py offers only validated generations by default
```

## Canonical fields

- **Staging key** — the key the archive is uploaded to first, held outside the
  `itsup.tar.gz.` generation prefix so it is never a generation or a restore
  target. Removed once the run resolves.
- **Completeness check** — the staged object's stored byte length compared to the
  local archive's byte length; equality is the gate that authorizes promotion.
- **Promotion** — the server-side copy of a verified-complete staged object to its
  `itsup.tar.gz.<timestamp>` name, followed by writing the validation marker. The
  final generation object is only ever created by this copy, never by the initial
  upload.
- **Validation marker** — a small companion object, keyed outside the
  `itsup.tar.gz.` generation prefix, written only after promotion. Its presence is
  the signal that a generation is validated; a legacy generation from before this
  contract carries none and is treated as unvalidated.
- **Retention** — keeps the newest ten validated generations, evicts unvalidated
  objects before validated ones, and runs only after promotion (never a pre-upload
  prune).
- **Restore selection** — `bin/restore.py` lists and default-restores only
  validated generations; an explicitly named archive key remains restorable so a
  legacy generation can still be recovered on demand.

## Known caveats

- The guarantee is forward-looking: generations written by an earlier, non-atomic
  version of the script carry no validation marker, so they are treated as
  unvalidated — never default-restored and evicted before any validated
  generation, though still recoverable by explicit key. They are not
  retroactively validated.
