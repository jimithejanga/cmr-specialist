#!/bin/sh
# Runs once on first `db` volume init (postgres entrypoint hook).
# Gives the registry operator service its own database on the same
# Postgres: agent data lives in `cmr`, registry tables in `cmr_registry`.
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
SELECT 'CREATE DATABASE cmr_registry' WHERE NOT EXISTS (
  SELECT FROM pg_database WHERE datname = 'cmr_registry')\gexec
SQL
echo "init-db: cmr_registry ready"
