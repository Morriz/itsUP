#!/usr/bin/env sh
. .venv/bin/activate

kill $(fuser 8888/tcp 2>/dev/null | awk '{ print $1 }') 2>/dev/null

PYTHONPATH=. python api/main.py main:app >logs/api.log 2>&1 &
