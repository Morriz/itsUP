---
id: 'project/adr/0001-itsup-cli-single-root'
type: 'adr'
scope: 'project'
description: 'itsup binds to one install root via ITSUP_ROOT rather than selecting a project from the current directory, because itsUP orchestrates exactly one host stack.'
date: '2026-06-22'
number: 1
---

# itsup CLI Binds to a Single Install Root — ADR

## Context

Making `itsup` a global command (so no caller has to `source env.sh`) forces a
choice about how it locates its data — `projects/`, `secrets/`, `upstream/`,
`tpl/`. The sibling tool `telec` is **cwd/project-aware**: it discovers the
project from the current working directory, because it serves many projects on a
developer's machine. itsup is structurally different — it is the orchestrator of
exactly **one** host's stack, and its data lives in one checkout.

A global CLI must resolve its root without relying on cwd (the brittleness we are
removing). The question is whether to make itsup discover its root from the
current directory (telec's model) or bind it to a fixed install.

## Decision

itsup binds to a **single install root**, resolved by `root()` as `ITSUP_ROOT`
(when set) else derived from the installed package location. It does **not**
select a project or root from the current working directory.

`itsup` gains telec's *ergonomics* — global, no sourcing, cwd-independent — but
deliberately not telec's *binding*. Running `itsup` from any directory operates
on the one configured install, never on cwd.

## Consequences

- **Positive.** Global invocation with zero sourcing; cwd-independent and
  therefore safe from the activation/working-directory failures that motivated
  this. Single, unambiguous source of truth for where the stack lives, which
  systemd, `start-api.sh`, and the self-update all share via `ITSUP_ROOT`.
- **Negative.** itsup cannot manage multiple independent itsUP installs from one
  shell by `cd`-ing between them; switching installs means changing
  `ITSUP_ROOT`. This is acceptable: a host runs one stack.
- **Follow-on.** All cwd-relative `Path("…")` reads must move behind `root()`,
  and `ITSUP_ROOT` must be set in every non-interactive runtime environment.

## Alternatives Considered

- **cwd/project-aware (telec's model).** Rejected: itsUP is not multi-project;
  cwd-discovery would reintroduce a "must be in the right directory" footgun for
  no benefit, since there is only ever one stack per host.
- **Absolute-path shebang on `bin/itsup`.** Rejected: host-specific and
  un-committable, fixes only the interpreter (not root resolution or PATH), and
  is not how a properly installed CLI is distributed.
