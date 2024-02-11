#!/usr/bin/env sh
. lib/functions.sh

echo "Starting bin/start-cmd-listener.sh in the background..."
bin/start-cmd-listener.sh &

echo "Starting proxy..."
bin/start-proxy.sh

echo "Starting doup api..."
dcd up
