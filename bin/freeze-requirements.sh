#!/usr/bin/env sh

pip freeze -q -r requirements.txt | sed '/freeze/,$ d' >requirements-prod.txt
