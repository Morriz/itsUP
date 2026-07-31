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

# The Traefik access log keeps the writer's inode across rotation. Guard this
# fixed template here so lint catches a return to a signal-based reopen before
# the template can be installed on a host.
logrotate_template="samples/logrotate/itsup"
logrotate_violation=0
if [ ! -r "$logrotate_template" ]; then
    echo "Traefik logrotate template is not readable: $logrotate_template"
    logrotate_violation=1
else
    traefik_stanza="$(awk '
        /^\{\{ROOT\}\}\/logs\/access\.log \{$/ { in_stanza = 1 }
        in_stanza { print }
        in_stanza && /^\}$/ { exit }
    ' "$logrotate_template")"
    if [ -z "$traefik_stanza" ]; then
        echo "Traefik access-log stanza is missing from $logrotate_template"
        logrotate_violation=1
    elif ! printf '%s\n' "$traefik_stanza" | grep -Eq '^[[:space:]]*copytruncate[[:space:]]*$'; then
        echo "Traefik access-log stanza must use copytruncate"
        logrotate_violation=1
    fi
    if printf '%s\n' "$traefik_stanza" | grep -Eq '^[[:space:]]*postrotate([[:space:]]|$)|USR1'; then
        echo "Traefik access-log stanza must not use postrotate or USR1"
        logrotate_violation=1
    fi
fi

if [ "$logrotate_violation" -ne 0 ]; then
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
