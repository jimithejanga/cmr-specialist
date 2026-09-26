#!/bin/sh
# Shed nightly backup: pg_dump -> timestamped file, prune older than $BACKUP_KEEP_DAYS.
# Runs inside the compose `backup` service; also runnable on any host with pg_dump.
set -eu
OUTDIR="${BACKUP_DIR:-/backups}"
KEEP="${BACKUP_KEEP_DAYS:-14}"
mkdir -p "$OUTDIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FILE="$OUTDIR/cmr-$STAMP.sql.gz"
pg_dump | gzip > "$FILE"
find "$OUTDIR" -name 'cmr-*.sql.gz' -mtime +"$KEEP" -delete
echo "backup wrote $FILE"
