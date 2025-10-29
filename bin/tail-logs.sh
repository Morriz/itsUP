#!/usr/bin/env sh

tail -f -n 10 logs/*.log | bin/format-logs.py
