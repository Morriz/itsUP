#!/bin/sh

## Usage:
##   . ./export-env.sh $project; $COMMAND

project=$1
env_file=upstream/$project/.env

if [ -f "$env_file" ]; then
  unamestr=$(uname)
  if [ "$unamestr" = 'Linux' ]; then
    export $(grep -v '^#' "$env_file" | xargs -d '\n')
  elif [ "$unamestr" = 'FreeBSD' ] || [ "$unamestr" = 'Darwin' ]; then
    export $(grep -v '^#' "$env_file" | xargs -0)
  fi
fi
