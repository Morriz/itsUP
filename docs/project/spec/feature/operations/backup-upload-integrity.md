---
description: Acceptance scenario for bin/backup.py's S3 upload integrity — a backup
  generation counts as a restore point only after its transfer is verified complete and
  marked validated, so an interrupted or truncated upload never becomes a validated
  generation, retention never lets an unvalidated object displace a validated one, and
  bin/restore.py only ever offers validated generations.
delivered_by: [backup-upload-not-atomic-retention-unvalidated]
---

# Backup Upload Integrity — Spec

## Required reads

- @docs/project/spec/runtime-operations.md

## What it is

`bin/backup.py` uploads the `itsup.tar.gz` archive to S3 under a timestamped
generation name `itsup.tar.gz.<timestamp>` and retains the newest ten
generations; `bin/restore.py` restores the newest generation by default. A
generation is only a real restore point once its upload is proven complete.

The upload proves completeness before a generation counts. After the archive is
uploaded, its stored byte length is compared to the local archive's; only on a
match is the generation marked **validated** by writing a small companion
validation marker (a separate object outside the `itsup.tar.gz.` generation
prefix). An interrupted, truncated, or otherwise incomplete upload never reaches
the match, so it never gets a validation marker — it is at most an unvalidated
object that no consumer treats as a restore point.

Both consumers gate on the validation marker, not on recency or name alone:

- **Retention** keeps the newest ten **validated** generations. When it must
  evict to stay within the cap it removes unvalidated objects before validated
  ones, so an object that never passed the completeness check can never displace
  one that did. Pruning runs only after a generation is validated, so a failed
  run never deletes a validated generation.
- **Restore** offers only validated generations, so a partial or legacy
  unvalidated object can never be selected as the generation to restore.

The business value is that the disaster-recovery substrate cannot be silently
poisoned: a partial upload cannot masquerade as a restore point, recency cannot
preserve a corrupt object at the expense of a good one, and restore cannot hand
back an unverified archive — the failure that would otherwise surface only at
restore time, when it can least be tolerated.

### Use cases

The scenario below is bound by functional tests that drive the real upload,
retention, and restore paths with the S3 service faked at the process boundary,
simulating a transfer that lands fewer bytes than the archive holds.

#### UC-BUI1: Only a verified-complete upload becomes a validated restore point

```gherkin
Given validated generations already exist in the bucket
And bin/backup.py uploads a new archive to S3 but the transfer lands only part of its bytes
When the upload step completes
Then the incomplete upload is not marked validated
And no unvalidated object is left able to displace a validated generation
And every pre-existing validated generation is still present
And bin/restore.py offers only the validated generations for restore
```

## Canonical fields

- **Validation marker** — a small companion object, keyed outside the
  `itsup.tar.gz.` generation prefix, written only after the uploaded archive's
  byte length is verified equal to the local archive's. Its presence is the sole
  signal that a generation is a validated restore point.
- **Completeness check** — the uploaded object's stored byte length compared to
  the local archive's byte length; equality is the gate that authorizes writing
  the validation marker.
- **Retention** — keeps the newest ten validated generations; evicts unvalidated
  objects before validated ones; runs only after the current generation is
  validated (never a pre-upload prune).
- **Restore selection** — `bin/restore.py` lists and restores only generations
  that carry a validation marker; an unvalidated object is never an eligible
  restore target.

## Known caveats

- The guarantee is forward-looking for the marker: generations written by an
  earlier, non-atomic version of the script carry no validation marker, so they
  are treated as unvalidated — never offered for restore and evicted before any
  validated generation. They are not retroactively validated.
