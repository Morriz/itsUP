# Run a one-off, interuptable command in a container
drun() {
  $image = $1
  shift
  eval docker run --rm -it \
    -v $PWD/certs:/app/certs \
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
  dc_ proxy proxy $@
}
dcpx() {
  dcx_ proxy proxy $@
}

# Run docker compose in an upstream
dcu() {
  project=$1
  shift
  [ -z "$project" ] && echo "No upstream project given!" && return 1
  dc_ upstream/$project $project $@
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

# remove a specific certificate
certrm() {
  dom=$1
  [ -z "$dom" ] && echo "No domain given!" && return 1
  sudo rm -rf certs/$dom data/letsencrypt/archive/$dom data/letsencrypt/live/$dom data/letsencrypt/renewal/$dom*
}
