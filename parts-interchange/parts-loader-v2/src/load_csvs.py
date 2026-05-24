"""
Phase 2 — CSV → PostgreSQL

Streams each CSV file into PostgreSQL using COPY FROM STDIN, which is
orders of magnitude faster than row-by-row INSERTs.

Usage:
  python load_csvs.py --csv-dir /tmp/parts_csvs [--init-schema]
  python load_csvs.py --reset-db   # drop all tables (pair with generate --fresh)

  --init-schema  Run create_all() to create tables (safe to rerun).
  --reset-db     Drop and recreate the public schema (wipes all data).
                 Always pair this with generate_csvs.py --fresh so IDs
                 are in sync.  After reset, re-run with --init-schema.

Environment variables (all optional, have defaults):
  db_host, db_port, db_user, db_pass, db_name
"""

import argparse
import os
import sys
import time

import psycopg2

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# FK-dependency order — each table's referenced tables appear before it
LOAD_ORDER = [
    'manufacturer',
    'year',
    'make',
    'model',         # → make
    'trim',
    'engine',
    'category',
    'subcategory',   # → category
    'image',         # → manufacturer
    'part',          # → manufacturer
    'car',           # → year, make, model, trim, engine, manufacturer
    'diagram',       # → image, category, subcategory
    'part_images',   # → part, image
    'diagram_parts', # → diagram, part
    'car_parts',     # → car, part
    'car_diagrams',  # → car, diagram
]

SERIAL_TABLES = [
    'manufacturer', 'year', 'make', 'model', 'trim', 'engine',
    'category', 'subcategory', 'image', 'part', 'car', 'diagram',
]

# Tables whose CSVs don't include every schema column.
# Explicit column lists prevent COPY from choking on schema additions.
COPY_COLUMNS = {
    'image': '(id, name, bucket_path, url, alt_text, saved, uploaded, manufacturer_id)',
}


def _connect():
    from config import get_psycopg2_params
    return psycopg2.connect(**get_psycopg2_params())


def init_schema():
    from config import get_db_url
    from sqlalchemy import create_engine
    from parts_interchange_common.models import Base
    engine = create_engine(get_db_url())
    Base.metadata.create_all(engine)
    engine.dispose()
    print("Schema ready.")


def reset_db():
    """Drop and recreate the public schema, wiping all tables and data."""
    conn = _connect()
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("DROP SCHEMA public CASCADE;")
    cur.execute("CREATE SCHEMA public;")
    cur.execute("GRANT ALL ON SCHEMA public TO PUBLIC;")
    cur.close()
    conn.close()
    print("Database reset. Run load with --init-schema to recreate tables.")



def load(csv_dir: str, create_tables: bool = False, make: str = None):
    if create_tables:
        init_schema()

    conn = _connect()
    conn.autocommit = False
    cur = conn.cursor()

    if make:
        make_dir = os.path.join(csv_dir, make.lower())
        if not os.path.isdir(make_dir):
            print(f"No CSV directory found for make '{make}': {make_dir}")
            cur.execute("SET session_replication_role = DEFAULT;")
            conn.commit()
            cur.close()
            conn.close()
            return
        make_dirs = [make_dir]
    else:
        make_dirs = sorted([
            os.path.join(csv_dir, d) for d in os.listdir(csv_dir)
            if os.path.isdir(os.path.join(csv_dir, d))
        ])

    if not make_dirs:
        print("No per-make CSV subdirectories found — nothing to load.")
        cur.execute("SET session_replication_role = DEFAULT;")
        conn.commit()
        cur.close()
        conn.close()
        return

    total_start = time.time()

    try:
        for table in LOAD_ORDER:
            for make_dir in make_dirs:
                csv_path = os.path.join(make_dir, f'{table}.csv')
                if not os.path.exists(csv_path):
                    continue

                make_name = os.path.basename(make_dir)
                size_mb = os.path.getsize(csv_path) / 1_000_000
                t0 = time.time()
                label = f"{make_name}/{table}"
                sys.stdout.write(f"  {label:<32} ({size_mb:>8.1f} MB) ... ")
                sys.stdout.flush()

                cols = COPY_COLUMNS.get(table, '')
                with open(csv_path, 'r', encoding='utf-8') as f:
                    cur.copy_expert(f'COPY {table} {cols} FROM STDIN CSV', f)
                conn.commit()

                elapsed = time.time() - t0
                print(f"done in {elapsed:.1f}s")

    except Exception:
        conn.rollback()
        raise

    # After bulk load with explicit IDs, reset each SERIAL sequence so that
    # subsequent application inserts get correct next values.
    print("\nResetting sequences...")
    for table in SERIAL_TABLES:
        cur.execute(
            f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
            f"COALESCE(MAX(id), 0)) FROM {table};"
        )
    conn.commit()

    total = time.time() - total_start
    print(f"\nLoad complete in {total:.0f}s ({total/60:.1f} min)")

    cur.close()
    conn.close()


def main():
    parser = argparse.ArgumentParser(description='Bulk-load CSV files into PostgreSQL via COPY')
    parser.add_argument('--csv-dir', default='/tmp/parts_csvs',
                        help='Directory containing CSV files from generate_csvs.py')
    parser.add_argument('--make',
                        help='Load only this manufacturer, e.g. --make acura')
    parser.add_argument('--init-schema', action='store_true',
                        help='Run create_all() before loading (creates tables if they do not exist)')
    parser.add_argument('--reset-db', action='store_true',
                        help='Drop and recreate the public schema (wipes all data). '
                             'Pair with generate_csvs.py --fresh. Does not load any CSVs.')
    args = parser.parse_args()

    if args.reset_db:
        reset_db()
        return

    if not os.path.isdir(args.csv_dir):
        print(f"CSV directory not found: {args.csv_dir}")
        sys.exit(1)

    load(args.csv_dir, args.init_schema, args.make)


if __name__ == '__main__':
    main()
