#!/usr/bin/env sh
. .venv/bin/activate

[ ! -d ".venv" ] && python -m venv .venv
pip install -r requirements-prod.txt
