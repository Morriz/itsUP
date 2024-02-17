#!/usr/bin/env sh
. .venv/bin/activate

pip freeze -q -r requirements.txt | sed '/freeze/,$ d' >requirements-prod.txt
