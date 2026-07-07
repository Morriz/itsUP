#!/usr/bin/env bash

echo "Formatting code"

# Scope: when telec passes FILES_FROM (a NUL-delimited file of changed paths),
# format exactly those Python files; otherwise format the project's source dirs.
files=()
if [ -n "${FILES_FROM:-}" ] && [ -f "$FILES_FROM" ]; then
    while IFS= read -r -d '' path; do
        case "$path" in *.py) files+=("$path") ;; esac
    done < "$FILES_FROM"
    if [ "${#files[@]}" -eq 0 ]; then
        echo "No Python files in scope; nothing to format."
        exit 0
    fi
else
    files=(api lib)
fi

echo "Running isort"
uv run isort "${files[@]}"

echo "Running black"
uv run black "${files[@]}"
