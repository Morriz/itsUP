#!/usr/bin/env sh

# not in use (yet) but meant for running this repo in docker
# and being able to run docker-compose commands on the host

mkfifo hostpipe >/dev/null 2>&1

here=$(pwd)
out=$(pwd)/hostpipe.txt
grep="grep -E"
[ $(uname) = "Darwin" ] && grep="grep -e"

git="git fetch origin main && git reset --hard origin/main"

while true; do
  cmd=$(cat ./hostpipe)
  # cmd="cd upstream/test && docker compose up -d"
  echo "Received command: $cmd"
  if echo $cmd | $grep "^cd [0-9a-zA-Z/_-]* && docker compose "; then
    eval "$cmd; cd $here" >$out
  elif echo $cmd | $grep "^docker run --rm --name certbot "; then
    eval "$cmd" >$out
  elif echo $cmd | $grep "^git pull"; then
    eval "$git" >$out
  else
    echo "Invalid command: $cmd"
  fi
done
