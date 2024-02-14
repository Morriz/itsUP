#!/usr/bin/env sh
. .venv/bin/activate

python -m unittest discover -s . -p '*_test.py'
