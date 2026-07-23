---
description:
  Acceptance scenario for bin/backup.py's argument boundary — a non-destructive
  invocation such as --help or an unrecognised argument exits without running the
  production backup, so the script can be inspected without shipping an archive
  to S3.
delivered_by: [backup-script-has-no-safe-invocation]
---

# Backup Safe Invocation — Spec

## Required reads

- @docs/project/spec/runtime-operations.md

## What it is

`bin/backup.py` performs the nightly production backup: it loads infra secrets,
runs the per-project adapter dumps, builds the `itsup.tar.gz` archive of
`upstream/` and `proxy/`, and uploads it to S3 with keep-10 rotation. The
scheduled units invoke it bare — with no arguments — and that argument-free
invocation is the one that runs the backup.

An argument boundary guards the destructive path: the script parses its
arguments before doing any work, so a `--help` request prints usage and an
unrecognised argument prints the argument error, and both exit without loading
secrets, building an archive, or uploading anything. Only the bare, argument-free
invocation the scheduled units use proceeds to run the backup.

The business value is that the script can be inspected — the reflexive `--help`
probe an operator or agent reaches for is safe — without publishing an
off-schedule archive to the backup bucket.

### Use cases

The scenario below is bound by exactly one functional test in
`tests/operations/test_backup_safe_invocation.py`, which invokes the real script
through its own command surface against a per-test root, with the external
services it would otherwise reach unreachable at the process boundary.

#### UC-BSI1: An inspection probe exits without running the backup

```gherkin
Given bin/backup.py is invoked as an inspection probe rather than a scheduled run
When it runs with --help or with an unrecognised argument
Then it exits without loading secrets, building an archive, or uploading to S3
```

## Canonical fields

- **Inputs** — the invocation arguments passed to `bin/backup.py`: none (the
  scheduled run), `--help`, or an unrecognised flag.
- **Output** — for `--help`, usage text and a success exit; for an unrecognised
  argument, an argument error and a non-zero exit; in both cases no secret load,
  no archive build, and no S3 upload. Only the argument-free invocation runs the
  backup.

## Known caveats

- The boundary lives inside the script's `main()` entry point, so importing
  `bin/backup.py` as a module — as `bin/restore.py` does for `DB_FILE` and
  `build_s3_client` — never parses arguments and never triggers a backup.
