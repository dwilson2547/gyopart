#!/bin/bash
# Load generated CSV files into PostgreSQL.
#
# Environment variables:
#   CSV_DIR   — directory containing CSVs from run_generate.sh (default: /tmp/parts_csvs)
#   MAKE      — if set, only load this manufacturer (e.g. MAKE=acura)
#   DB_HOST   — postgres host     (default: localhost)
#   DB_PORT   — postgres port     (default: 5432)
#   DB_USER   — postgres user     (default: parts_user)
#   DB_PASS   — postgres password (default: parts_pass)
#   DB_NAME   — database name     (default: parts_interchange)
#
# Pass --init-schema to create tables before loading (first run only).
#
# Examples:
#   ./run_load.sh --init-schema
#   MAKE=acura ./run_load.sh
#   DB_HOST=192.168.1.10 CSV_DIR=/data/csvs ./run_load.sh

CSV_DIR="${CSV_DIR:-/tmp/parts_csvs}"

MAKE_ARG=""
if [ -n "$MAKE" ]; then
  MAKE_ARG="--make $MAKE"
fi

docker run --rm \
  -v "${CSV_DIR}:/csvs:ro" \
  -e db_host="${DB_HOST:-localhost}" \
  -e db_port="${DB_PORT:-5432}" \
  -e db_user="${DB_USER:-parts_user}" \
  -e db_pass="${DB_PASS:-parts_pass}" \
  -e db_name="${DB_NAME:-parts_interchange}" \
  --network host \
  parts-loader-v2 \
  python load_csvs.py --csv-dir /csvs $MAKE_ARG "$@"
