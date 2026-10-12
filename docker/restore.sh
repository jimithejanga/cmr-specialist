#!/bin/sh
# Restore proof for the office-PC pilot: restore the NEWEST backup to a
# scratch database and verify it opens. A backup you never restored is a rumor.
# Usage (on the office PC, inside docker/):
#   ./restore.sh                          # restore newest /backups file to cmr_restore_check
#   BACKUP_FILE=/backups/cmr-....sql.gz ./restore.sh
# Compose equivalent (runs against the `db` service):
#   docker compose exec -e PGPASSWORD=$POSTGRES_PASSWORD db \
#     sh -c "gunzip -c /backups/<FILE> | psql -U cmr -d cmr_restore_check"
set -eu
BACKUP_DIR="${BACKUP_DIR:-/backups}"
FILE="${BACKUP_FILE:-$(ls -t "$BACKUP_DIR"/cmr-*.sql.gz 2>/dev/null | head -1)}"
if [ -z "${FILE:-}" ] || [ ! -f "$FILE" ]; then
  echo "no backup found in $BACKUP_DIR (run backup.sh first)" >&2
  exit 1
fi
PGHOST="${PGHOST:-db}"
PGUSER="${PGUSER:-cmr}"
PGDATABASE="${PGDATABASE:-cmr}"
SCRATCH="${SCRATCH_DB:-cmr_restore_check}"
echo "restoring $FILE -> scratch db $SCRATCH on $PGHOST"
psql -h "$PGHOST" -U "$PGUSER" -d postgres -c "DROP DATABASE IF EXISTS $SCRATCH;"
psql -h "$PGHOST" -U "$PGUSER" -d postgres -c "CREATE DATABASE $SCRATCH;"
gunzip -c "$FILE" | psql -h "$PGHOST" -U "$PGUSER" -d "$SCRATCH" -q
# Minimal sanity: cases table exists and is countable.
psql -h "$PGHOST" -U "$PGUSER" -d "$SCRATCH" -c "SELECT count(*) AS cases FROM cases;"
echo "restore proof OK: $FILE opens as $SCRATCH"
