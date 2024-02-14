#!/usr/bin/env sh
. .venv/bin/activate

for i in $(cat requirements.txt) $(cat requirements-test.txt); do
  echo "Updating $i"
  pip install --upgrade $i
done

bin/requirements-freeze.sh
