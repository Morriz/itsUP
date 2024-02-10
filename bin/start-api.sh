#!/usr/bin/env sh

.venv/bin/uvicorn api.main:app --port 8888 --host "0.0.0.0"
