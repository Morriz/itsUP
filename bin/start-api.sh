#!/usr/bin/env sh
. .venv/bin/activate

kill $(fuser 8888/tcp 2>/dev/null | awk '{ print $1 }')

PYTHONPATH=. python api/main.py main:app >logs/error.log 2>&1 &
