---
description:
  How pylint reports success and failure to a calling shell — the category
  bitmask it accumulates into its exit status, the score gate that can override
  it, and the --fail-on escape hatch that forces a failing status. Curated for
  itsUP's lint gate, which consumes that status.
---

# pylint — Exit Status Reference

Curated from the pylint distribution itsUP pins (`pylint 4.0.6`, resolved by
`uv.lock`). Line references are into that installed package, which is the
version-accurate authority for the semantics itsUP's `bin/lint.sh` depends on.

## The status is a category bitmask

pylint keeps a running `msg_status` and bit-ORs one flag into it per emitted
message category (`pylint/lint/pylinter.py:1248`):

```python
self.msg_status |= MSG_TYPES_STATUS[message_definition.msgid[0]]
```

The flags are (`pylint/constants.py:43`):

| Category | Prefix | Value |
| --- | --- | --- |
| Fatal | `F` | 1 |
| Error | `E` | 2 |
| Warning | `W` | 4 |
| Refactor | `R` | 8 |
| Convention | `C` | 16 |
| Information | `I` | 0 |

Because the values are OR-ed, a status is read bitwise, not as an enum: `28` is
`16 | 8 | 4` — convention, refactor, and warning messages present, with no error
and no fatal. `32` is separate and is not a message category; it is emitted
directly when pylint cannot write its `--output` file
(`pylint/lint/run.py:236`).

A caller that only needs to know whether pylint is satisfied compares the status
to zero. Decoding individual bits narrows the check to selected categories and
is only correct when that narrowing is intended.

## The score gate can return success despite messages

The exit decision (`pylint/lint/run.py:244-260`) is ordered:

1. `--exit-zero` — exit `0` unconditionally.
2. `--fail-on` matched — exit `msg_status or 1`, always non-zero.
3. A score was produced — exit `0` when `score >= fail_under`, otherwise
   `msg_status or 1`.
4. No score was produced — exit `msg_status`.

Step 3 is the consequential one: **messages alone do not guarantee a non-zero
status.** When the run's score reaches `fail_under`, pylint exits `0` with its
findings printed. `fail_under` defaults to `10.0`, so under default
configuration any message at all drops the score below the threshold and the
status is non-zero — but a project that lowers `fail_under` buys itself a green
exit with findings on screen.

## `--fail-on` adds a failure condition; it does not narrow the run

`--fail-on=<symbols>` is evaluated at step 2, ahead of the score gate, and is
satisfied when any named symbol appears among the emitted messages
(`pylint/lint/pylinter.py:540-541`):

```python
def any_fail_on_issues(self) -> bool:
    return any(x in self.fail_on_symbols for x in self.stats.by_msg.keys())
```

It therefore guarantees a failing status for the named symbols even when the
score would otherwise clear `fail_under`. It does **not** restrict the run to
those symbols: every other check still runs, still prints, and still contributes
its bit to `msg_status` through the ordinary path. Reading `--fail-on=X` as
"only X can fail this run" inverts its meaning.

## Sources

- https://pylint.readthedocs.io/en/stable/user_guide/usage/run.html

## See Also

- docs/project/spec/feature/quality/lint-gate-status-propagation.md — the itsUP gate that consumes this status.
