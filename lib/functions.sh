# Run a one-off, interuptable command in a container
drun() {
  $image = $1
  shift
  eval docker run --rm -it \
    -v $PWD/data:/app/data \
    -v $PWD/proxy:/app/proxy \
    -v $PWD/upstream:/app/upstream \
    $image sh -c "'$@'"
}

dc_() {
  dir=$1
  project=$2
  part=$3
  shift
  shift
  cmd=$@
  shift
  [ -z "$dir" ] && echo "No dir given!" && return 1
  [ -z "$project" ] && echo "No project given!" && return 1
  [ -z "$cmd" ] && echo "No command given!" && return 1
  if [ "$cmd" = "up" ]; then
    cmd="$cmd -d"
  fi
  if [ "$part" = "up" ]; then
    . bin/export-env.sh $project
    docker compose --project-directory $dir -p $project -f $dir/docker-compose.yml pull
    cmd="$cmd --remove-orphans"
  fi
  eval "export HOST_GID=$(id -g daemon) && docker compose --project-directory $dir -p $project -f $dir/docker-compose.yml $cmd $@"
}

dcx_() {
  dir=$1
  project=$2
  svc=$3
  shift
  shift
  shift
  dc_ $dir $project exec $svc sh -c "'$@'"
}

# Run docker compose in the proxy
dcp() {
  if [ "$1" = "up" ] || [ "$1" = "restart" ]; then
    # Smart update with optional service arg
    service=$2
    if [ -n "$service" ]; then
      .venv/bin/python -c "from lib.proxy import update_proxy; update_proxy('$service')"
    else
      .venv/bin/python -c "from lib.proxy import update_proxy; update_proxy()"
    fi
  else
    dc_ proxy proxy $@
  fi
}
dcpx() {
  dcx_ proxy proxy $@
}

# Run docker compose in an upstream
dcu() {
  project=$1
  shift
  [ -z "$project" ] && echo "No upstream project given!" && return 1

  # Use rollout for up/restart for zero-downtime
  if [ "$1" = "up" ] || [ "$1" = "restart" ]; then
    cmd=$1
    service=$2
    if [ -n "$service" ]; then
      echo "Rolling out $service in $project..."
      (cd upstream/$project && docker rollout $service)
    else
      # No specific service, do all services
      for svc in $(cd upstream/$project && docker compose config --services); do
        echo "Rolling out $svc in $project..."
        (cd upstream/$project && docker rollout $svc)
      done
    fi
  else
    dc_ upstream/$project $project $@
  fi
}
dcux() {
  project=$1
  shift
  dcx_ upstream/$project $project $@
}

# Run docker compose command in all upstreams
dca() {
  [ -z "$@" ] && echo "No arguments given!" && return 1
  for upstream in $(ls -d upstream/*); do
    project=$(basename $upstream)
    dcu $project $@
  done
}
