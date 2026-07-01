#!/usr/bin/env bash
. .venv/bin/activate

echo "Running lint checks"

# Scope: when telec passes FILES_FROM (a NUL-delimited file of changed paths),
# lint exactly those Python files; otherwise lint the project's source dirs.
files=()
if [ -n "${FILES_FROM:-}" ] && [ -f "$FILES_FROM" ]; then
    while IFS= read -r -d '' path; do
        case "$path" in *.py) files+=("$path") ;; esac
    done < "$FILES_FROM"
    if [ "${#files[@]}" -eq 0 ]; then
        echo "No Python files in scope; skipping lint."
        exit 0
    fi
else
    files=(api lib)
fi

echo "Running pylint"
pylint --enable=C0415 --fail-on=C0415 "${files[@]}"

echo "Running mypy"
mypy "${files[@]}"
