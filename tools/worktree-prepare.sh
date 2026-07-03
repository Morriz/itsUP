#!/usr/bin/env bash
# Worktree build-env prep for the TeleClaude work lifecycle.
#
# The lifecycle builds each todo in a linked git worktree at trees/<slug>/ and
# needs an isolated Python env there. itsUP's `make install` refuses to run in a
# worktree (bin/lib/assert-canonical-checkout.sh) because it binds GLOBAL host
# state — the ~/.local/bin/itsup symlink plus an editable install — to the repo
# path, and a worktree's path is transient. This script does only the
# worktree-SAFE subset: a local .venv and editable install pinned to the
# worktree's own code. It never touches ~/.local/bin or any host binding, so
# global/host state stays bound to the canonical checkout alone.
#
# The lifecycle invokes this from the canonical checkout root with the slug as $1.
set -euo pipefail

SLUG="${1:?worktree-prepare: slug argument required}"
CANONICAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKTREE="${CANONICAL_ROOT}/trees/${SLUG}"

if [ ! -d "${WORKTREE}" ]; then
    echo "✗ worktree not found: ${WORKTREE}" >&2
    exit 1
fi

cd "${WORKTREE}"

# Local venv + editable install, pinned to THIS worktree's code. No global
# symlink, no host binding — the safe subset of `make install` for a worktree.
if [ ! -d .venv ]; then
    python3 -m venv .venv
fi
.venv/bin/pip install -q -e ".[test]"

echo "✓ Prepared worktree ${SLUG}: local .venv + editable install (no global binding)"
