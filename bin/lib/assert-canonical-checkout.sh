#!/usr/bin/env bash
# Guard: refuse to run from a linked git worktree.
#
# Source (never exec) this from any entrypoint that binds global or host state
# to the repo location — the ~/.local/bin/itsup symlink, an editable install, or
# systemd/launchd units carrying absolute repo paths. Such state must be bound
# only from the canonical checkout: a linked git worktree keeps `.git` as a file
# (a `gitdir:` pointer) while the canonical checkout keeps it as a directory, and
# a worktree's path is transient, so binding global/host state to it breaks the
# instant the worktree is cleaned up.
#
# The caller must have set REPO_ROOT. Optional: GUARD_OP names the entrypoint for
# the refusal message (e.g. "make install-runtime").
: "${REPO_ROOT:?assert-canonical-checkout: REPO_ROOT must be set before sourcing}"

if [ -f "${REPO_ROOT}/.git" ]; then
    echo "✗ Refusing: run ${GUARD_OP:-this} from the canonical itsUP checkout, not a linked worktree." >&2
    echo "  here: ${REPO_ROOT} (this is a git worktree)" >&2
    echo "  It binds global/host state to the repo path; a worktree's path is transient." >&2
    exit 1
fi
