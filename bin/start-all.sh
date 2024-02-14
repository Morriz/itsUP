#!/usr/bin/env sh
. lib/functions.sh

echo "Starting proxy..."
bin/start-proxy.sh

echo "Starting doup api..."
bin/start-api.sh
