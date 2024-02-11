image=morriz/doup:main

dcd() {
  cmd=$1
  shift
  [ -z "$cmd" ] && echo "No command given!" && return 1
  d=
  r=
  if [ "$cmd" = "up" ]; then
    d="-d"
    r="--remove-orphans"
  fi
  docker compose $cmd $d $r $@
}

dcdx() {
  eval docker compose exec api sh -c "'$@'"
}

drun() {
  eval docker run --rm -it --name doup \
    -v $PWD/certs:/app/certs \
    -v $PWD/data:/app/data \
    -v $PWD/hostpipe:/app/hostpipe \
    -v $PWD/proxy:/app/proxy \
    -v $PWD/upstream:/app/upstream \
    $image sh -c "'$@'"
}

# Run docker compose in the proxy
dcp() {
  cmd=$1
  shift
  [ -z "$cmd" ] && echo "No command given!" && return 1
  d=
  r=
  if [ "$cmd" = "up" ]; then
    d="-d"
    r="--remove-orphans"
  fi
  docker compose --project-directory proxy -p proxy -f proxy/docker-compose.yml $cmd $d $r $@
}

# Run docker compose in an upstream
dcu() {
  project=$1
  shift
  [ -z "$project" ] && echo "No upstream project given!" && return 1
  cmd=$1
  shift
  [ -z "$cmd" ] && echo "No command given!" && return 1
  d=
  r=
  if [ "$cmd" = "up" ] && [ -z "$1" ] && [ "$1" != "-d" ]; then
    d="-d"
    r="--remove-orphans"
  fi
  docker compose --project-directory upstream/$project -p $project -f upstream/$project/docker-compose.yml $cmd $d $r $@
}

# Run docker compose command in all upstreams
dca() {
  cmd=$1
  shift
  [ -z "$cmd" ] && echo "No command given!" && return 1
  d=
  r=
  if [ "$cmd" = "up" ]; then
    # we can't do any blocking calls here, so:
    d="-d"
    r="--remove-orphans"
  fi
  for upstream in $(ls -d upstream/*); do
    project=$(basename $upstream)
    dcu $project $cmd $d $r $@
  done
}

# remove a specific certificate
certrm() {
  dom=$1
  [ -z "$dom" ] && echo "No domain given!" && return 1
  sudo rm -rf certs/$dom data/letsencrypt/archive/$dom data/letsencrypt/live/$dom data/letsencrypt/renewal/$dom*
}
