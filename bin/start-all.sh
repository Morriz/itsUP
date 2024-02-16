#!/usr/bin/env sh
. lib/functions.sh

echo "Starting proxy..."
bin/start-proxy.sh

echo "Starting itsUP api..."
bin/start-api.sh
