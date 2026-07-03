#!/usr/bin/env sh
# itsUP shell completion (bash + zsh).
#
# Sourced from your shell rc by `make install`; safe to source by hand too:
#   source /path/to/itsUP/bin/itsup-completion.sh
#
# itsup is a Click CLI, so completion is generated on the fly from the installed
# console-script — no static completion file to keep in sync. zsh callers must
# have run compinit first (rc frameworks like oh-my-zsh do this), because the
# generated script registers via compdef.
if command -v itsup >/dev/null 2>&1; then
    if [ -n "${ZSH_VERSION:-}" ]; then
        eval "$(_ITSUP_COMPLETE=zsh_source itsup)"
    elif [ -n "${BASH_VERSION:-}" ]; then
        eval "$(_ITSUP_COMPLETE=bash_source itsup)"
    fi
fi
