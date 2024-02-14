#!/usr/bin/env sh
. .venv/bin/activate

dirs="api lib"

echo "Running lint checks"

echo "Running pylint"
pylint $dirs

echo "Running mypy"
mypy $dirs
