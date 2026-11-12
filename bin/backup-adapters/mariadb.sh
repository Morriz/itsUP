#!/usr/bin/env sh
# MariaDB backup adapter.
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
#   MARIADB_SERVICE  compose service running the engine (default: mariadb)
# The clients run as root inside the container. The root password is read from the
# container's own MARIADB_ROOT_PASSWORD, so the host never holds or passes it.
set -eu

cmd="${1:-}"
dir="${2:-}"
service="${MARIADB_SERVICE:-mariadb}"

[ -z "$cmd" ] && echo "mariadb adapter: no command given (dump|restore)" >&2 && exit 2
[ -z "$dir" ] && echo "mariadb adapter: no project upstream dir given" >&2 && exit 2
[ -d "$dir" ] || { echo "mariadb adapter: dir not found: $dir" >&2; exit 2; }

# Run a MariaDB client as root in the engine container. The container's shell reads
# the password from its own environment and hands it to the client through
# MYSQL_PWD, keeping it off every command line. -T disables TTY for piping.
dc_root() {
  # shellcheck disable=SC2016 # expanded by the container's shell, not this one
  (cd "$dir" && docker compose exec -T "$service" sh -c '
    : "${MARIADB_ROOT_PASSWORD:?is not set in the engine container}"
    export MYSQL_PWD="$MARIADB_ROOT_PASSWORD"
    exec "$@"
  ' sh "$@")
}

do_dump() {
  out="$dir/_backup"
  mkdir -p "$out"
  # A dump takes its final name only once its client exits cleanly, so _backup/
  # never offers a truncated dump for restore.
  rm -f "$out/accounts.sql" "$out/databases.sql"
  trap 'rm -f "$out/accounts.sql.partial" "$out/databases.sql.partial"' EXIT
  # Accounts, roles and grants as portable SQL. --insert-ignore makes every CREATE
  # conditional, so the output loads into an engine that already holds some of them.
  dc_root mariadb-dump --user=root --system=users --insert-ignore >"$out/accounts.sql.partial"
  echo "mariadb adapter: dumping all databases"
  # One snapshot across every database. The mysql system schema stays out: its
  # accounts travel in accounts.sql, the rest belongs to the engine it runs in.
  dc_root mariadb-dump --user=root --all-databases --ignore-database=mysql \
    --single-transaction --add-drop-database --routines --events \
    >"$out/databases.sql.partial"
  mv "$out/accounts.sql.partial" "$out/accounts.sql"
  mv "$out/databases.sql.partial" "$out/databases.sql"
  echo "mariadb adapter: dump written to $out"
}

do_restore() {
  src="$dir/_backup"
  for dump in accounts.sql databases.sql; do
    [ -f "$src/$dump" ] || { echo "mariadb adapter: no dump at $src ($dump missing)" >&2; exit 1; }
  done
  echo "mariadb adapter: restoring accounts and all databases"
  # One client session, which stops at the first error. Accounts precede the
  # databases so the definers of views, routines and events exist.
  #
  # The dump's accounts replace the credentials of every account they name. Two
  # accounts belong to this engine rather than to the dump: root, whose password is
  # the container's MARIADB_ROOT_PASSWORD, and the image's healthcheck account,
  # whose password lives in the data directory. Their rows are set aside before the
  # dump's accounts load and put back right after.
  {
    echo "CREATE TEMPORARY TABLE mysql.backup_adapter_engine_accounts AS"
    echo "  SELECT * FROM mysql.global_priv WHERE User IN ('root', 'healthcheck');"
    cat "$src/accounts.sql"
    echo "REPLACE INTO mysql.global_priv SELECT * FROM mysql.backup_adapter_engine_accounts;"
    echo "FLUSH PRIVILEGES;"
    cat "$src/databases.sql"
  } | dc_root mariadb --user=root
  echo "mariadb adapter: restore complete"
}

case "$cmd" in
  dump) do_dump ;;
  restore) do_restore ;;
  *) echo "mariadb adapter: unknown command '$cmd' (dump|restore)" >&2; exit 2 ;;
esac
