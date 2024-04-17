#!/usr/bin/env sh

tail -f logs/*.log | while read line; do if
  echo $line | egrep "\{.*}" >/dev/null
  json=$(echo $line | egrep -oh "\{.*}" | jq '.')
then echo $line | awk -v json="$json" -F "\{.*}" '{printf "%s%s%s\n",$1,json,$2}'; fi; done
