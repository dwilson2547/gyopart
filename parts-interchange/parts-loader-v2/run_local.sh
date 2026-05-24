#!/bin/bash
# Run generate and/or load directly in WSL (no Docker) against the Postgres container.
#
# Usage:
#   MAKE=acura ./run_local.sh generate
#   ./run_local.sh load --init-schema
#   MAKE=acura ./run_local.sh all        # generate then load (adds --init-schema on first run)
#
# Environment variables (all have defaults):
#   MAKE      — manufacturer to process, e.g. MAKE=acura (omit to use skip flags in car_configs)
#   SAVE_DIR  — root of unpacked scraper data (default: /mnt/z/parts_direct_recovery)
#   CSV_DIR   — where to write / read CSV files (default: /tmp/parts_csvs)
#   DB_HOST   — default: localhost
#   DB_PORT   — default: 5432
#   DB_USER   — default: parts_user
#   DB_PASS   — default: parts_pass
#   DB_NAME   — default: parts_interchange
#   CONDA_ENV — conda environment to use     (default: py39)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_DIR="$SCRIPT_DIR/src"
CONDA_ENV="${CONDA_ENV:-py39}"

# Export env vars consumed by config.py and car_configs.py
export save_dir="${SAVE_DIR:-/mnt/z/parts_direct_recovery}"
export db_host="${DB_HOST:-localhost}"
export db_port="${DB_PORT:-5432}"
export db_user="${DB_USER:-parts_user}"
export db_pass="${DB_PASS:-parts_pass}"
export db_name="${DB_NAME:-parts_interchange}"

CSV_DIR="${CSV_DIR:-/home/daniel/documents/workspace/parts_interchange/csvs}"
mkdir -p "$CSV_DIR"

MAKE_ARG=""
if [ -n "$MAKE" ]; then
  MAKE_ARG="--make $MAKE"
fi

CMD="${1:-help}"
shift || true

_pip_install() {
  conda run -n "$CONDA_ENV" pip install -q -r "$SRC_DIR/requirements.txt"
}

_generate() {
  conda run -n "$CONDA_ENV" python "$SRC_DIR/generate_csvs.py" \
    --output-dir "$CSV_DIR" $MAKE_ARG "$@"
}

_load() {
  conda run -n "$CONDA_ENV" python "$SRC_DIR/load_csvs.py" \
    --csv-dir "$CSV_DIR" $MAKE_ARG "$@"
}

_init_state() {
  conda run -n "$CONDA_ENV" python "$SRC_DIR/init_state.py" \
    --output-dir "$CSV_DIR" "$@"
}

case "$CMD" in
  setup)
    echo "Installing requirements into conda env '$CONDA_ENV'..."
    _pip_install
    echo "Done."
    ;;
  init-state)
    # Bootstrap state.json from the current DB (run once when DB already has data)
    _init_state "$@"
    ;;
  generate)
    _generate "$@"
    ;;
  load)
    _load "$@"
    ;;
  all)
    _generate
    _load --init-schema "$@"
    ;;
  reset-db)
    # Wipe all tables from the DB. Always pair with generate --fresh.
    _load --reset-db
    ;;
  fresh)
    # Full restart: wipe DB, wipe state/CSVs, regenerate, reload.
    # MAKE env var controls which manufacturer(s) to process.
    echo "=== Full restart: wiping DB and state ==="
    _load --reset-db
    _generate --fresh
    _load --init-schema
    ;;
  *)
    echo "Usage: [ENV_VARS] $0 <command> [args]"
    echo ""
    echo "Commands:"
    echo "  setup        Install Python requirements into conda env"
    echo "  init-state   Bootstrap state.json from existing DB (add manufacturers without full reload)"
    echo "  generate     Generate CSV files from JSON data (incremental, preserves state)"
    echo "  load         Load CSV files into PostgreSQL (incremental, no truncation)"
    echo "  all          generate then load (--init-schema on first run)"
    echo "  reset-db     Wipe all DB tables (pair with generate --fresh)"
    echo "  fresh        Full restart: reset-db + generate --fresh + load --init-schema"
    echo ""
    echo "Normal workflow (adding manufacturers one at a time):"
    echo "  ./run_local.sh setup                      # first time only"
    echo "  MAKE=acura ./run_local.sh generate"
    echo "  MAKE=acura ./run_local.sh load --init-schema"
    echo "  MAKE=bmw ./run_local.sh generate          # state.json carries IDs forward"
    echo "  MAKE=bmw ./run_local.sh load"
    echo ""
    echo "Full restart (wipe everything and reload):"
    echo "  MAKE=acura ./run_local.sh fresh           # or --all for all non-skipped"
    echo ""
    echo "Recovery (DB has data but no state.json):"
    echo "  ./run_local.sh init-state                 # read DB → write state.json"
    echo "  MAKE=bmw ./run_local.sh generate"
    echo "  ./run_local.sh load"
    ;;
esac
