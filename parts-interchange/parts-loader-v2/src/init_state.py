"""
Bootstrap state.json from an existing database.

Run this once when you have data already loaded and want to add more
manufacturers without reloading everything from scratch.

Usage:
  python init_state.py [--output-dir /path/to/csvs]
"""

import argparse
import json
import os

import psycopg2

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = 'state.json'


def build_state(csv_dir: str):
    from config import get_psycopg2_params
    conn = psycopg2.connect(**get_psycopg2_params())
    cur = conn.cursor()

    def seq_map(rows, n):
        return {'d': dict(rows), 'n': n}

    # Manufacturers — key is lowercase name
    cur.execute("SELECT LOWER(name), id FROM manufacturer;")
    mfr_rows = cur.fetchall()
    cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM manufacturer;")
    mfr_n = cur.fetchone()[0]

    # Years — key is year string (e.g. "2023")
    cur.execute("SELECT name, id FROM year;")
    year_rows = cur.fetchall()
    cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM year;")
    year_n = cur.fetchone()[0]

    # Makes — key is select_value
    cur.execute("SELECT select_value, id FROM make;")
    make_rows = cur.fetchall()
    cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM make;")
    make_n = cur.fetchone()[0]

    # Models — key is "make_id::select_value"
    cur.execute("SELECT make_id || '::' || select_value, id FROM model;")
    model_rows = cur.fetchall()
    cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM model;")
    model_n = cur.fetchone()[0]

    # Trims — key is select_value
    cur.execute("SELECT select_value, id FROM trim;")
    trim_rows = cur.fetchall()
    cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM trim;")
    trim_n = cur.fetchone()[0]

    # Engines — key is select_value
    cur.execute("SELECT select_value, id FROM engine;")
    engine_rows = cur.fetchall()
    cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM engine;")
    engine_n = cur.fetchone()[0]

    # Categories — key is name
    cur.execute("SELECT name, id FROM category;")
    cat_rows = cur.fetchall()
    cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM category;")
    cat_n = cur.fetchone()[0]

    # Subcategories — key is "category_id::name"
    cur.execute("SELECT category_id || '::' || name, id FROM subcategory;")
    subcat_rows = cur.fetchall()
    cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM subcategory;")
    subcat_n = cur.fetchone()[0]

    # Per-manufacturer table sequences (globally unique IDs even though maps reset per-mfr)
    cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM image;")
    image_seq = cur.fetchone()[0]

    cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM part;")
    part_seq = cur.fetchone()[0]

    cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM car;")
    car_seq = cur.fetchone()[0]

    cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM diagram;")
    diagram_seq = cur.fetchone()[0]

    # Processed = manufacturers already fully loaded in the DB
    processed = [row[0] for row in mfr_rows]

    cur.close()
    conn.close()

    state = {
        'mfrs':        seq_map(mfr_rows, mfr_n),
        'years':       seq_map(year_rows, year_n),
        'makes':       seq_map(make_rows, make_n),
        'models':      seq_map(model_rows, model_n),
        'trims':       seq_map(trim_rows, trim_n),
        'engines':     seq_map(engine_rows, engine_n),
        'categories':  seq_map(cat_rows, cat_n),
        'subcats':     seq_map(subcat_rows, subcat_n),
        'image_seq':   image_seq,
        'part_seq':    part_seq,
        'car_seq':     car_seq,
        'diagram_seq': diagram_seq,
        'processed':   processed,
    }

    os.makedirs(csv_dir, exist_ok=True)
    path = os.path.join(csv_dir, STATE_FILE)
    with open(path, 'w') as f:
        json.dump(state, f, indent=2)

    print(f"State written to: {path}")
    print(f"  Manufacturers already loaded: {', '.join(processed) or '(none)'}")
    print(f"  Next IDs: manufacturer={mfr_n}, year={year_n}, make={make_n}, "
          f"model={model_n}, trim={trim_n}, engine={engine_n}, "
          f"category={cat_n}, subcategory={subcat_n}, "
          f"image={image_seq}, part={part_seq}, car={car_seq}, diagram={diagram_seq}")
    print(f"\nYou can now run generate_csvs.py for additional manufacturers.")


def main():
    parser = argparse.ArgumentParser(
        description='Bootstrap state.json from the current database contents'
    )
    parser.add_argument('--output-dir', default='/tmp/parts_csvs',
                        help='CSV directory where state.json will be written '
                             '(should match --output-dir used for generate_csvs.py)')
    args = parser.parse_args()
    build_state(args.output_dir)


if __name__ == '__main__':
    main()
