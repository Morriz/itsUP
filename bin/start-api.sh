#!/usr/bin/env bash
# Repo-local, cwd-independent: resolve the repo root from this script's own
# location and run the API with the venv python at an absolute path. The editable
# install makes lib/commands importable without PYTHONPATH, and no env.sh sourcing
# is needed on the runtime path.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# The API resolves its install root from ITSUP_ROOT; set it for the launched
# process so root() never falls back to the package location.
export ITSUP_ROOT="${REPO_ROOT}"

kill $(fuser 8888/tcp 2>/dev/null | awk '{ print $1 }') 2>/dev/null

"${REPO_ROOT}/.venv/bin/python" "${REPO_ROOT}/api/main.py" main:app >"${REPO_ROOT}/logs/api.log" 2>&1 &
