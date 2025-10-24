#!/usr/bin/env sh

tail -f -n 100 logs/*.log | bin/format-logs.py
