#!/usr/bin/env sh

tail -f logs/*.log | bin/format-logs.py
