#!/bin/bash
# Optional developer convenience: activate the project venv and enable `itsup`
# shell completion for this session. Sourcing is NOT required to run itsup —
# `make install` puts a global `itsup` on your PATH (~/.local/bin/itsup) that
# works from any directory without sourcing.
# Usage: source env.sh

# Get the directory where this script lives
ITSUP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

# Activate the virtual environment (activates the venv interpreter for
# development and exposes the venv's itsup console-script for this session).
if [ -f "$ITSUP_ROOT/.venv/bin/activate" ]; then
    source "$ITSUP_ROOT/.venv/bin/activate"
    echo "✓ Activated Python virtual environment"
else
    echo "⚠ Virtual environment not found. Run 'make install' first."
    return 1
fi

# Enable shell completion for itsup
if command -v itsup >/dev/null 2>&1; then
    # Detect shell and set up completion
    if [ -n "$BASH_VERSION" ]; then
        eval "$(_ITSUP_COMPLETE=bash_source itsup)"
        echo "✓ Bash completion enabled for itsup"
    elif [ -n "$ZSH_VERSION" ]; then
        # zsh completion needs compdef; ensure completion system is loaded first
        if ! command -v compdef >/dev/null 2>&1; then
            autoload -Uz compinit && compinit >/dev/null
        fi
        eval "$(_ITSUP_COMPLETE=zsh_source itsup)"
        echo "✓ Zsh completion enabled for itsup"
    fi
fi
