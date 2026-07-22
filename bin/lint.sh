#!/usr/bin/env bash

echo "Running lint checks"

# Python source never selects its own interpreter. Packaged commands are
# generated in .venv/bin; standalone jobs are invoked by the venv interpreter.
launcher_violation=0
while IFS= read -r -d '' path; do
    if [ -x "$path" ]; then
        echo "Python source must not be executable: $path"
        launcher_violation=1
    fi
    if head -n 1 "$path" | grep -Eq '^#!.*python'; then
        echo "Python source must not carry a shebang: $path"
        launcher_violation=1
    fi
    if grep -Eq '_VENV_PYTHON|[._]execv\(' "$path"; then
        echo "Python source must not bootstrap an interpreter: $path"
        launcher_violation=1
    fi
done < <(find bin -maxdepth 1 -type f -name '*.py' -print0)

if [ "$launcher_violation" -ne 0 ]; then
    exit 1
fi

# Scope: when telec passes FILES_FROM (a NUL-delimited file of changed paths),
# lint exactly those Python files; otherwise lint the project's source dirs.
files=()
if [ -n "${FILES_FROM:-}" ] && [ -f "$FILES_FROM" ]; then
    while IFS= read -r -d '' path; do
        case "$path" in
            bin/*.py) ;;
            *.py) files+=("$path") ;;
        esac
    done < "$FILES_FROM"
    if [ "${#files[@]}" -eq 0 ]; then
        echo "No Python files in scope; skipping lint."
        exit 0
    fi
else
    files=(api lib)
fi

echo "Running pylint"
uv run pylint --enable=C0415 --fail-on=C0415 "${files[@]}"

echo "Running mypy"
uv run mypy "${files[@]}"
