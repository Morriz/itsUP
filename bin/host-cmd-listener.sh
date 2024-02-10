#!/usr/bin/env sh

# not in use (yet) but meant for running this repo in docker
# and being able to run docker-compose commands on the host

while true; do
  cmd=$(cat /cmd-pipe)
  # check if cmd starts with "docker compoer":
  if [ "${cmd:0:6}" = "docker compose" ]; then
    # run the cmd
    eval "$cmd"
  else
    echo "Invalid command: $cmd"
  fi
done
