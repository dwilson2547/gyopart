#!/bin/bash
# Generate CSV files from scraped JSON data.
#
# Environment variables:
#   SAVE_DIR   — root of the unpacked scraper data (default: /home/daniel/rsync-dump)
#   CSV_DIR    — where to write output CSVs       (default: /tmp/parts_csvs)
#   MAKE       — if set, only process this manufacturer (e.g. MAKE=gm)
#
# Examples:
#   ./run_generate.sh
#   MAKE=gm CSV_DIR=/data/csvs ./run_generate.sh
#   MAKE=gm ./run_generate.sh --resume   # append to existing CSVs after a crash

SAVE_DIR="${SAVE_DIR:-/home/daniel/rsync-dump}"
CSV_DIR="${CSV_DIR:-/tmp/parts_csvs}"

MAKE_ARG=""
if [ -n "$MAKE" ]; then
  MAKE_ARG="--make $MAKE"
fi

mkdir -p "$CSV_DIR"

docker run --rm \
  -v "${SAVE_DIR}:/data:ro" \
  -v "${CSV_DIR}:/output" \
  -e save_dir=/data \
  parts-loader-v2 \
  python generate_csvs.py --output-dir /output $MAKE_ARG "$@"
