---
description: Acceptance scenario for bin/backup.py's S3 upload integrity — a restore-point
  name is published only for an archive whose transfer completed and was verified, so an
  interrupted or truncated upload never lands under a valid generation name and retention
  rotates only validated restore points.
delivered_by: [backup-upload-not-atomic-retention-unvalidated]
---

# Backup Upload Integrity — Spec

## Required reads

- @docs/project/spec/runtime-operations.md

## What it is

`bin/backup.py` uploads the `itsup.tar.gz` archive to S3 under a timestamped
restore-point name `itsup.tar.gz.<timestamp>` and prunes to the newest ten
generations. A restore-point name is a promise: `bin/restore.py` treats every
`itsup.tar.gz.<timestamp>` object as a recoverable generation and restores the
newest by default.

The upload keeps that promise atomically. The archive is first uploaded to a
staging key held outside the `itsup.tar.gz.` restore-point prefix; the upload is
then verified for completeness — the staged object's byte length must equal the
local archive's; and only a verified-complete staged object is promoted to its
final `itsup.tar.gz.<timestamp>` name by a server-side copy. An interrupted,
truncated, or otherwise incomplete transfer therefore never appears under a
restore-point name — it leaves at most a staging object, which is cleaned up and
which neither `bin/restore.py` nor the keep-ten rotation ever considers.

Because only verified-complete archives ever bear a restore-point name, the
keep-ten retention — which ranks generations by recency — rotates over validated
restore points alone. An unverified object can neither occupy a retained slot nor
evict a validated generation.

The business value is that the disaster-recovery substrate cannot be silently
poisoned: a partial upload can never masquerade as a restore point, and recency
cannot preserve a corrupt object at the expense of a good one — the failure that
would otherwise surface only at restore time, when it can least be tolerated.

### Use cases

The scenario below is bound by exactly one functional test that drives the real
upload path with the S3 service faked at the process boundary, simulating a
transfer that lands fewer bytes than the archive holds.

#### UC-BUI1: An incomplete upload never publishes a restore point

```gherkin
Given bin/backup.py uploads the archive to S3 but the transfer lands only part of its bytes
And validated restore-point generations already exist in the bucket
When the upload step completes
Then no object exists under the final itsup.tar.gz.<timestamp> restore-point name for that run
And every pre-existing validated generation is still present
```

## Canonical fields

- **Staging key** — the key the archive is uploaded to first, held outside the
  `itsup.tar.gz.` restore-point prefix so neither retention nor restore ever
  treats it as a generation. Removed once the run resolves.
- **Completeness check** — the staged object's stored byte length compared to the
  local archive's byte length; equality is the promotion gate.
- **Promotion** — the server-side copy of a verified-complete staged object to its
  `itsup.tar.gz.<timestamp>` restore-point name. The restore-point object is only
  ever created by this copy, never by the initial upload.
- **Retention** — the keep-ten rotation over `itsup.tar.gz.<timestamp>` objects,
  unchanged in ranking; it operates only on promoted (validated) restore points
  because unverified objects never bear the prefix it rotates.

## Known caveats

- The integrity guarantee is forward-looking: it governs objects this upload path
  writes. A restore-point object published by an earlier, non-atomic version of
  the script is not retroactively validated or removed by this contract.
