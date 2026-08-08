---
description: 'itsUP removes its entire test corpus — the spec-bound suite under tests/ and the colocated unittest modules in lib/ and api/ — because Python supplies no external standard at the unit level and the corpus was authored by the same agents whose work it judges; verification moves to driving the running system.'
date: '2026-08-08'
number: 4
---

# Remove the Test Corpus — ADR

## Context

itsUP holds two distinct bodies of test code. Under `tests/` sit 26 files
organized by domain, each binding a feature-spec scenario through
`@pytest.mark.spec` and sharing the `isolated_itsup_root` fixture — the shape the
platform doctrine prescribed. Alongside them, seven `lib/*_test.py` modules and
`api/main_test.py` remain from before that migration: `unittest.TestCase` classes
asserting against internals, bound to no scenario, dating in part to the initial
commit.

`software-development/policy/testing` now makes test authorship opt-in: no test
is authored in a project that has not declared otherwise, and holding a corpus
is explicitly not a declaration. itsUP therefore has to decide what happens to
the corpus it holds rather than inherit it by inertia.

The reasoning is `general/principle/verification-independence`: a change is
verified only against a standard originating outside the session that produced
it. That principle is substrate-sensitive in a way that matters here. A compiled
language whose type system rejects illegal states supplies such a standard for
free at the unit level, which is why colocated unit tests remain required in
Rust. Python supplies none. In itsUP every layer of the corpus was written by
the same agents that wrote the code it judges, so what a green run demonstrates
is agreement rather than correctness.

The colocated modules fail the test even on the prior doctrine — they bind no
scenario and assert against internals, which the language policy forbids
outright. The `tests/` suite is the harder case, because scenario binding is
precisely the mechanism designed to supply an external standard. It is included
anyway: the mechanism only holds when the scenario's author and the test's
binder are genuinely distinct, and that separation is not evidenced across this
corpus.

A concrete cost is already visible. Of the 33 open pylint findings across `api`
and `lib`, 18 sit inside these test files and cannot be resolved where they are:
editing an unbound test trips the scenario-binding predicate. Routine
maintenance is already stalled on a corpus whose value is the question at issue.

## Decision

itsUP will author no tests, and will not retain the corpus it holds. The choice
is removal rather than freezing, covering `tests/` in full, the seven
`lib/*_test.py` modules, and `api/main_test.py`, together with the runner,
pytest and coverage configuration, and test-only dependencies that exist to
serve them.

The `test` action will be unbound from itsUP's `code` scope in its own
`teleclaude.yml`, so a source change no longer owes a test run. `log-check`
stays bound and is unaffected.

Verification is what the global default already sanctions and never bans:
driving the real running system in-session — invoking the CLI, exercising the
API, observing the daemon — plus the checkpoint obligations that already fire on
a code change. Both supply a standard the authoring session did not write.

Feature-spec scenarios under `docs/project/spec/feature/` are **retained**. They
are human-facing behavioral contracts and remain the description of what itsUP
does; only their bound tests go. A scenario with no bound test is a documented
contract, not a gap to fill.

## Alternatives considered

**Freeze the corpus — keep and run it, author nothing new.** This is the
brownfield middle path the global default explicitly permits, and it preserves
whatever regression signal the suite carries. Rejected: it keeps a corpus whose
green result is uninformative for the reason above, while continuing to pay its
maintenance and its drag on unrelated work — the lint todo is already blocked by
exactly that. Freezing defers the decision at ongoing cost rather than making
it.

**Remove only the colocated modules, keep `tests/`.** The colocated modules are
indefensible under any doctrine, and the spec-bound suite is the part built to
the intended shape. Rejected because the distinction does not survive the
author/binder question: a bound scenario supplies an external standard only when
someone other than the binder authored it, and keeping the suite on the strength
of its form while that is unevidenced would preserve the appearance of
verification without the property.

**Keep the suite as a refactoring safety net.** Rejected on recovery cost: an
agent rewrites a module in minutes, so the insurance argument that funds a suite
in human-paced development does not apply. What insurance still pays for is
silent, irreversible failure, and that is not what this corpus covers.

## Consequences

- No pre-written regression net. A defect that a straightforward test would have
  caught now reaches the running system, where the checkpoint obligations and
  live verification are what surface it. This is the accepted cost of the
  decision, not an oversight.
- 18 of the 33 open pylint findings disappear with the files rather than being
  fixed in place, and the scenario-binding predicate stops obstructing routine
  maintenance of them. The outstanding lint work narrows to the 15 findings in
  production code.
- `bin/test.sh`, the pytest and coverage configuration in `pyproject.toml`, and
  the test-only dependencies become dead surface and go with the corpus.
- The `code` scope in `teleclaude.yml` currently excludes `tests/**` and
  `**/*_test.py`; those exclusions become vestigial once the paths are gone.
- Reviewers apply no test-coverage or test-quality lane to itsUP. A review
  finding demanding a test is a misreading of this decision.
- Reversing this is cheap in one direction only: the deleted corpus is
  recoverable from git, but re-adopting authorship requires a declaration
  against the global default and the reasoning that overturns this record.
