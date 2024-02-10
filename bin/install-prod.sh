#!/usr/bin/env sh

[ ! -d ".venv" ] && python -m venv .venv
.venv/bin/pip install -r requirements-prod.txt
