---
description: Acceptance scenarios for the itsup CLI's location-transparent
  discovery and authoring surface — project-name discovery, per-project file
  listing, cwd-usable path reporting, the fail-safe non-interactive secret
  round-trip, and the interactive-only guard on the human secret editor.
delivered_by:
  - itsup-agent-authoring-surface
---

# Agent Authoring Surface — Spec

## Required reads

@docs/project/spec/secrets-management.md

## What it is

The itsup CLI is location-transparent for executing commands but was opaque
for authoring: nothing told a non-interactive caller which projects exist,
which files make up a project or a secret, or how to edit a secret without a
blocking terminal editor. This surface makes discovery and authoring as
location-transparent as execution: project names and constituent files are
listable read-only from any machine and any cwd, every reported file location
is usable from the caller's working directory, and the secret round-trip
(decrypt → edit → encrypt → commit) is safe without a terminal — a plaintext
edit is never silently lost to the `secrets/` gitignore.

The business value is that agents can operate the GitOps config/secrets flow
end to end with their own file-editing tools, without knowing the install
root and without a human at a terminal — while the fail-closed commit path
guarantees no secret edit evaporates and no plaintext leaks into git.

### Use cases

Each scenario below is bound by exactly one functional test in
`tests/cli/test_agent_authoring_surface.py`, driving the real command surface
with real sops/age and real git repositories.

#### UC-DISC1: Listing the configured project names

```gherkin
Given an install root with configured projects
And a directory under projects/ that carries no project configuration
When the caller lists the projects
Then each configured project name is printed on its own line
And the unconfigured directory is not listed
```

#### UC-DISC2: Listing the files that constitute a project

```gherkin
Given a configured project with its compose and config files
And an encrypted secret file for that project
When the caller lists that project's files
Then every file in the project's directory is reported
And the project's secret file is reported
```

#### UC-DISC3: An unknown project name fails

```gherkin
Given an install root whose projects do not include the requested name
When the caller lists the files of the requested name
Then the command exits non-zero
```

#### UC-PATH1: Reported locations are usable from a foreign cwd

```gherkin
Given the caller's working directory is not the install root
When a command reports a file location
Then the reported location is an absolute path to an existing file
```

#### UC-RT1: A plaintext secret edit is committed encrypted

```gherkin
Given a decrypted project secret edited on disk
And the secrets repository shows no tracked changes
When the caller commits
Then the encrypted secret at the repository head decrypts to the edited content
And the plaintext file is removed
```

#### UC-RT2: Commit refuses when encryption is unavailable

```gherkin
Given a plaintext secret exists
And the encryption tool is unavailable
When the caller commits
Then the command exits non-zero
And no new commit is created in the secrets repository
```

#### UC-ED1: The interactive editor refuses non-interactive callers

```gherkin
Given a caller without an interactive terminal
When the caller invokes the interactive secret editor
Then the command exits non-zero without opening an editor
And the encrypted secret file is unchanged
```

## Canonical fields

- Discovery and listing are read-only and sit on the anywhere-allowed side of
  the host command gate (`project/spec/cli`).
- Path-reporting contract and the non-interactive round-trip are specified in
  `project/spec/cli` (Discovery & authoring) and
  `project/spec/secrets-management` (Non-interactive round-trip).

## See Also

- docs/project/spec/cli.md
- docs/project/design/itsup-cli.md
