#!/usr/bin/env sh
# Postgres backup adapter.
#
# Contract (see project/design/backup-restore):
#   dump <project-upstream-dir>     write a consistent logical dump under <dir>/_backup/
#   restore <project-upstream-dir>  load that dump back into the running instance
#
# Both verbs operate against the live container via the compose-exec pattern: the
# adapter cd's into the project's upstream dir (which holds docker-compose.yml) so
# `docker compose` targets the running stack. Adapters never touch S3 — the mother
# script (bin/backup.py) owns archiving/upload and bin/restore.py owns download.
#
# Tunables (env):
#   PG_SERVICE  compose service running the engine (default: postgres)
#   PGUSER      superuser for dump/restore (default: postgres)
# pg_dumpall/pg_dump run as the postgres OS user inside the container (peer auth),
# so no password is required.
set -eu

cmd="${1:-}"
dir="${2:-}"
service="${PG_SERVICE:-postgres}"
user="${PGUSER:-postgres}"

[ -z "$cmd" ] && echo "postgres adapter: no command given (dump|restore)" >&2 && exit 2
[ -z "$dir" ] && echo "postgres adapter: no project upstream dir given" >&2 && exit 2
[ -d "$dir" ] || { echo "postgres adapter: dir not found: $dir" >&2; exit 2; }

dc() {
  # docker compose against the project's upstream stack; -T disables TTY for piping.
  (cd "$dir" && docker compose exec -T "$service" "$@")
}

# List non-template databases, excluding the bootstrap 'postgres' db.
list_databases() {
  dc psql -U "$user" -d postgres -tAc \
    "SELECT datname FROM pg_database WHERE datistemplate = false AND datname <> 'postgres';"
}

do_dump() {
  out="$dir/_backup"
  mkdir -p "$out"
  # Roles/globals first so a restore can recreate owners before per-db data.
  dc pg_dumpall -U "$user" --globals-only >"$out/globals.sql"
  for db in $(list_databases); do
    [ -z "$db" ] && continue
    echo "postgres adapter: dumping database '$db'"
    dc pg_dump -U "$user" -Fc "$db" >"$out/$db.dump"
  done
  echo "postgres adapter: dump written to $out"
}

do_restore() {
  src="$dir/_backup"
  [ -f "$src/globals.sql" ] || { echo "postgres adapter: no dump at $src" >&2; exit 1; }
  # Globals first: roles/ownership must exist before per-database restore.
  dc psql -U "$user" -d postgres <"$src/globals.sql"
  for dump in "$src"/*.dump; do
    [ -e "$dump" ] || continue
    db="$(basename "$dump" .dump)"
    echo "postgres adapter: restoring database '$db'"
    # Create the target db if absent; ignore the already-exists error.
    dc createdb -U "$user" "$db" 2>/dev/null || true
    dc pg_restore -U "$user" -d "$db" --clean --if-exists --no-owner <"$dump"
  done
  echo "postgres adapter: restore complete"
}

case "$cmd" in
  dump) do_dump ;;
  restore) do_restore ;;
  *) echo "postgres adapter: unknown command '$cmd' (dump|restore)" >&2; exit 2 ;;
esac
