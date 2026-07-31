---
description:
  Acceptance scenario for the repository lint gate's status propagation — the
  lint script reports failure to its caller when either linter it runs reports a
  finding, so pylint findings can block a commit and a CI run rather than being
  printed and passed over.
delivered_by:
  - fix-bin-lint-sh-silently-swallows-pylint-fai
---

# Lint Gate Status Propagation — Spec

## What it is

`bin/lint.sh` is the repository's lint gate. It runs the project's guard checks,
then pylint, then mypy, over either an explicit scoped file set (`FILES_FROM`)
or the project's source directories. Its exit status is the only thing its
callers read: the `Makefile` `lint` target forwards it, the pre-commit `lint`
hook blocks a commit on it, and the CI checks step fails the build on it.

The gate reports failure when **either** linter reports a finding. Both run on
every invocation — a pylint finding does not suppress the mypy run — and the
status the script returns reflects both, so no tool's verdict is lost behind
another's. Any non-zero status from a linter is a finding; the gate does not
narrow that to selected message categories.

The business value is that the gate can actually fail. A lint gate whose status
reflects only one of the tools it runs cannot block anything the other tool
finds, and every reviewer who reads a passing result is trusting a check that
could not have failed.

### Use cases

#### UC-LGS1: A pylint finding fails the gate even when mypy is clean

```gherkin
Given the lint script runs pylint and mypy over a set of Python files
When pylint reports a finding and mypy reports none
Then the lint script exits non-zero
```

## Canonical fields

- **Inputs** — the scoped set of Python files to check, and the exit status each
  of the two linters returns for that set.
- **Output** — a single exit status for the run: zero when both linters report
  no findings, non-zero when either reports one.

## Known caveats

- pylint's own exit status is score-gated and can be zero with findings printed;
  the categories it encodes and the conditions under which it returns success are
  in the required read above. The gate treats any non-zero status as a finding
  and does not decode the bitmask.
- The scenario is exercised with the linters replaced at the process boundary, so
  it observes the gate's status arithmetic rather than either linter's own
  analysis, and stays independent of whatever findings the repository currently
  carries.

## See Also

- docs/third-party/pylint/exit-status.md — the categories pylint's status encodes and the conditions under which it returns success.
- docs/project/policy/repository-conventions.md — the fixed pre-commit ordering the gate runs within.
