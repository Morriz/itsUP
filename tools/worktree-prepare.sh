#!/usr/bin/env bash
# Worktree build-env prep for the TeleClaude work lifecycle.
#
# The lifecycle builds each todo in a linked git worktree at trees/<slug>/ and
# needs a Python env there. itsUP's `make install` refuses in a worktree
# (bin/lib/assert-canonical-checkout.sh) because it binds GLOBAL host state — the
# ~/.local/bin/itsup symlink plus an editable install — to a transient path.
#
# This does the worktree-SAFE prep: SYMLINK the worktree's .venv to the canonical
# root's .venv. No per-worktree virtualenv (those bloat the tree and cripple the
# editor/agent file ops), no editable re-install, no global binding. The shared
# .venv provides dependencies; pytest still imports the worktree's own source
# because it inserts the worktree cwd first on sys.path.
#
# The lifecycle invokes this from the canonical checkout root with the slug as $1.
set -euo pipefail

SLUG="${1:?worktree-prepare: slug argument required}"

# Confine the slug to the lifecycle's kebab-case grammar before it becomes a
# filesystem path. This rejects `/`, `..`, and any pathlike value, so the target
# below can only ever be a single segment directly under trees/ — no traversal.
if [[ ! "${SLUG}" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]]; then
    echo "✗ invalid slug (expected kebab-case, no path separators): ${SLUG}" >&2
    exit 1
fi

CANONICAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKTREE="${CANONICAL_ROOT}/trees/${SLUG}"

if [ ! -d "${WORKTREE}" ]; then
    echo "✗ worktree not found: ${WORKTREE}" >&2
    exit 1
fi

# Assert the target is an actual linked git worktree before mutating it — a
# linked worktree keeps .git as a FILE (a gitdir pointer), never a directory.
if [ ! -f "${WORKTREE}/.git" ]; then
    echo "✗ not a linked git worktree: ${WORKTREE}" >&2
    exit 1
fi

# The shared root .venv must already exist — worktree prep reuses it, never
# provisions Python. Provision the canonical checkout first with `make install`.
if [ ! -x "${CANONICAL_ROOT}/.venv/bin/python" ]; then
    echo "✗ canonical root .venv missing: ${CANONICAL_ROOT}/.venv" >&2
    echo "  Run 'make install' in the canonical checkout first." >&2
    exit 1
fi

# Replace any existing worktree-local .venv (real dir or stale link) with a
# relative symlink to the shared root .venv. Relative so it survives tree moves.
rm -rf "${WORKTREE}/.venv"
ln -s "../../.venv" "${WORKTREE}/.venv"

echo "✓ Prepared worktree ${SLUG}: .venv -> shared canonical .venv (no per-worktree venv)"
