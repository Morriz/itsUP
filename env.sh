#!/bin/bash
# Source this file to add itsup to your PATH
# Usage: source env.sh

# Get the directory where this script lives
ITSUP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

# Activate virtual environment
if [ -f "$ITSUP_ROOT/.venv/bin/activate" ]; then
    source "$ITSUP_ROOT/.venv/bin/activate"
    echo "✓ Activated Python virtual environment"
else
    echo "⚠ Virtual environment not found. Run 'make install' first."
    return 1
fi

# Add bin to PATH if not already there
if [[ ":$PATH:" != *":$ITSUP_ROOT/bin:"* ]]; then
    export PATH="$ITSUP_ROOT/bin:$PATH"
    echo "✓ Added itsup to PATH"
    echo "  You can now run: itsup --help"
else
    echo "✓ itsup already in PATH"
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
