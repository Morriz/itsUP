#!/usr/bin/env sh
. .venv/bin/activate

dirs="api lib"

echo "Running lint checks"

echo "Running pylint"
pylint --enable=C0415 --fail-on=C0415 $dirs

echo "Running mypy"
mypy $dirs
