"""
Phase 1 — JSON → CSV

Streams scraped JSON files into per-table CSV files that PostgreSQL's COPY
command can ingest directly.  Memory stays low because:
  - imgs.json and parts.json are streamed one entry at a time via ijson
  - tree.json is processed one year file at a time (already split by year)
  - Only compact str→int ID maps are held in memory

State is persisted to $CSV_DIR/state.json between runs so that each
per-manufacturer run produces *only new rows* — IDs never overlap and
shared entities (years, makes, trims, engines, categories) are not
re-emitted once they already have a DB ID.

Usage:
  python generate_csvs.py --output-dir /path/to/csvs --make acura
  python generate_csvs.py --output-dir /path/to/csvs --make bmw
  python generate_csvs.py --output-dir /path/to/csvs --all
  python generate_csvs.py --output-dir /path/to/csvs --fresh --make acura  # wipe state and restart
"""

import argparse
import csv
import json
import os
import shutil
from html.parser import HTMLParser
from io import StringIO
from typing import Optional

try:
    import ijson
    _IJSON = True
except ImportError:
    _IJSON = False
    print("Warning: ijson not installed — falling back to json.load() (higher RAM for large files)")
    print("         Install with: pip install ijson")

STATE_FILE = 'state.json'


# ---------------------------------------------------------------------------
# HTML stripping
# ---------------------------------------------------------------------------

class _Stripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self._buf = StringIO()

    def handle_data(self, d):
        self._buf.write(d)

    def get_data(self):
        return self._buf.getvalue()


def _strip_html(s: Optional[str]) -> Optional[str]:
    if not s:
        return s
    h = _Stripper()
    h.feed(s)
    return h.get_data()


def _clean_title(title: str, part_num: str) -> str:
    try:
        cleaned = '-'.join(title.replace(part_num, '').split('-')[:-1]).strip()
        return cleaned or title
    except Exception:
        return title


# ---------------------------------------------------------------------------
# Sequential ID map
# ---------------------------------------------------------------------------

class _IdMap:
    """Assigns monotonically increasing integer IDs to new keys."""

    def __init__(self, start: int = 1):
        self._d: dict = {}
        self._n: int = start

    def get_or_create(self, key) -> tuple:
        if key not in self._d:
            self._d[key] = self._n
            self._n += 1
            return self._d[key], True
        return self._d[key], False

    def get(self, key) -> Optional[int]:
        return self._d.get(key)

    def __contains__(self, key) -> bool:
        return key in self._d

    def to_dict(self) -> dict:
        return {'d': self._d, 'n': self._n}

    @classmethod
    def from_dict(cls, data: dict) -> '_IdMap':
        m = cls()
        m._d = data['d']
        m._n = data['n']
        return m


# ---------------------------------------------------------------------------
# Buffered CSV writers (one file per table, opened lazily)
# ---------------------------------------------------------------------------

class _Writers:
    _BUF = 4 * 1024 * 1024  # 4 MB write buffer per file

    def __init__(self, out_dir: str):
        self._dir = out_dir
        self._fh: dict = {}
        self._cw: dict = {}

    def write(self, table: str, row: list):
        if table not in self._cw:
            path = os.path.join(self._dir, f'{table}.csv')
            fh = open(path, 'a', newline='', encoding='utf-8', buffering=self._BUF)
            self._fh[table] = fh
            self._cw[table] = csv.writer(fh)
        self._cw[table].writerow(row)

    def close(self):
        for fh in self._fh.values():
            fh.close()
        self._fh.clear()
        self._cw.clear()


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

class Generator:

    def __init__(self, out_dir: str):
        os.makedirs(out_dir, exist_ok=True)
        self._out_dir = out_dir
        self._w: _Writers = None

        # Global maps — shared across all manufacturers, persisted in state.json
        self._mfrs       = _IdMap()
        self._years      = _IdMap()
        self._makes      = _IdMap()
        # Tuple keys encoded as "make_id::select_value" strings for JSON compatibility
        self._models     = _IdMap()
        self._trims      = _IdMap()
        self._engines    = _IdMap()
        self._categories = _IdMap()
        # Tuple keys encoded as "category_id::name" strings
        self._subcats    = _IdMap()

        # Per-manufacturer maps — reset each run but start from persisted offsets
        self._images: _IdMap = None
        self._parts:  _IdMap = None
        self._cars:   _IdMap = None

        # Global sequence offsets for per-manufacturer tables — persisted in state.json
        # so IDs never collide across manufacturers even though the maps are reset
        self._image_seq   = 1
        self._part_seq    = 1
        self._car_seq     = 1
        self._diagram_seq = 1

        # Manufacturers fully processed in prior runs (skip re-processing)
        self._processed: list = []

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _state_path(self) -> str:
        return os.path.join(self._out_dir, STATE_FILE)

    def load_state(self) -> bool:
        path = self._state_path()
        if not os.path.exists(path):
            return False
        with open(path) as f:
            s = json.load(f)
        self._mfrs       = _IdMap.from_dict(s['mfrs'])
        self._years      = _IdMap.from_dict(s['years'])
        self._makes      = _IdMap.from_dict(s['makes'])
        self._models     = _IdMap.from_dict(s['models'])
        self._trims      = _IdMap.from_dict(s['trims'])
        self._engines    = _IdMap.from_dict(s['engines'])
        self._categories = _IdMap.from_dict(s['categories'])
        self._subcats    = _IdMap.from_dict(s['subcats'])
        self._image_seq   = s.get('image_seq', 1)
        self._part_seq    = s.get('part_seq', 1)
        self._car_seq     = s.get('car_seq', 1)
        self._diagram_seq = s.get('diagram_seq', 1)
        self._processed  = s.get('processed', [])
        print(f"Loaded state: {len(self._processed)} manufacturer(s) already processed "
              f"({', '.join(self._processed) or 'none'})")
        return True

    def save_state(self):
        state = {
            'mfrs':        self._mfrs.to_dict(),
            'years':       self._years.to_dict(),
            'makes':       self._makes.to_dict(),
            'models':      self._models.to_dict(),
            'trims':       self._trims.to_dict(),
            'engines':     self._engines.to_dict(),
            'categories':  self._categories.to_dict(),
            'subcats':     self._subcats.to_dict(),
            'image_seq':   self._image_seq,
            'part_seq':    self._part_seq,
            'car_seq':     self._car_seq,
            'diagram_seq': self._diagram_seq,
            'processed':   self._processed,
        }
        with open(self._state_path(), 'w') as f:
            json.dump(state, f)

    def clear_csvs(self):
        """Remove all per-make CSV subdirectories."""
        for entry in os.listdir(self._out_dir):
            path = os.path.join(self._out_dir, entry)
            if os.path.isdir(path):
                shutil.rmtree(path)

    def _clear_make_dir(self, make_csv_dir: str):
        """Clear a single make's CSV directory before (re-)processing."""
        if os.path.isdir(make_csv_dir):
            for fname in os.listdir(make_csv_dir):
                if fname.endswith('.csv'):
                    os.remove(os.path.join(make_csv_dir, fname))
        os.makedirs(make_csv_dir, exist_ok=True)

    def clear_all(self):
        """Remove all per-make CSV dirs and state — full restart."""
        self.clear_csvs()
        path = self._state_path()
        if os.path.exists(path):
            os.remove(path)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(self, configs: dict):
        self.load_state()

        for name, cfg in configs.items():
            if cfg.get('skip'):
                print(f"Skipping {name} (skip=True in car_configs)")
                continue
            if name.lower() in self._processed:
                print(f"Skipping {name} (already processed in a previous run — "
                      f"use --fresh to reprocess from scratch)")
                continue
            print(f"\n=== {name} ===")
            make_csv_dir = os.path.join(self._out_dir, name.lower())
            self._clear_make_dir(make_csv_dir)
            self._w = _Writers(make_csv_dir)
            self._do_manufacturer(name, cfg)
            self._w.close()
            # Advance global offsets so the next manufacturer's IDs don't overlap
            self._image_seq   = self._images._n
            self._part_seq    = self._parts._n
            self._car_seq     = self._cars._n
            self._processed.append(name.lower())
            self.save_state()

        print(f"\nDone. CSVs written to: {self._out_dir}")

    # ------------------------------------------------------------------
    # Manufacturer
    # ------------------------------------------------------------------

    def _do_manufacturer(self, name: str, cfg: dict):
        mfr_id, is_new = self._mfrs.get_or_create(name.lower())
        if is_new:
            display = name[0].upper() + name[1:].lower()
            self._w.write('manufacturer', [mfr_id, display, cfg.get('base_url', '')])

        self._images = _IdMap(start=self._image_seq)
        self._parts  = _IdMap(start=self._part_seq)
        self._cars   = _IdMap(start=self._car_seq)

        data_dir = cfg['data_dir']

        imgs_file       = os.path.join(data_dir, 'imgs.json')
        parts_file      = os.path.join(data_dir, 'parts.json')
        tree_file       = os.path.join(data_dir, 'tree.json')
        split_tree_file = os.path.join(data_dir, 'tree_split.json')
        year_dir        = os.path.join(data_dir, 'years')

        if not os.path.exists(split_tree_file) or os.path.getsize(split_tree_file) == 0:
            if os.path.exists(tree_file):
                print("  Splitting tree by year (one-time)...")
                self._split_tree(tree_file, year_dir, split_tree_file)
            else:
                print(f"  Warning: no tree file found for {name}, skipping")

        if os.path.exists(imgs_file):
            print("  Processing images...")
            self._do_images(imgs_file, mfr_id, name.lower())
        else:
            print(f"  Warning: {imgs_file} not found")

        if os.path.exists(parts_file):
            print("  Processing parts...")
            self._do_parts(parts_file, mfr_id)
        else:
            print(f"  Warning: {parts_file} not found")

        if os.path.exists(split_tree_file):
            print("  Processing tree...")
            self._do_tree(split_tree_file, data_dir, mfr_id)

    def _split_tree(self, tree_file: str, year_dir: str, split_tree_file: str):
        with open(tree_file) as f:
            tree = json.load(f)
        os.makedirs(year_dir, exist_ok=True)
        split = {}
        for year, val in tree.items():
            if not isinstance(val, dict):
                continue
            year_path = os.path.join(year_dir, f'{year}.json')
            with open(year_path, 'w') as f:
                json.dump({year: val}, f)
            split[year] = os.path.join('years', f'{year}.json')
        with open(split_tree_file, 'w') as f:
            json.dump(split, f)

    # ------------------------------------------------------------------
    # Images
    # ------------------------------------------------------------------

    def _do_images(self, imgs_file: str, mfr_id: int, make_lower: str):
        count = 0
        if _IJSON:
            with open(imgs_file, 'rb') as f:
                for img_name, img_data in ijson.kvitems(f, ''):
                    self._write_image(img_name, img_data, mfr_id, make_lower)
                    count += 1
                    if count % 100_000 == 0:
                        print(f"    {count:,} images...")
        else:
            with open(imgs_file) as f:
                data = json.load(f)
            for img_name, img_data in data.items():
                self._write_image(img_name, img_data, mfr_id, make_lower)
                count += 1
        print(f"    {count:,} images total")

    def _write_image(self, img_name: str, img_data: dict, mfr_id: int, make_lower: str):
        img_id, is_new = self._images.get_or_create(img_name)
        if not is_new:
            return
        self._w.write('image', [
            img_id,
            img_name,
            f'{make_lower}/images/{img_name}',
            img_data.get('url'),
            img_data.get('alt'),
            img_data.get('saved', True),
            img_data.get('uploaded', False),
            mfr_id,
        ])

    # ------------------------------------------------------------------
    # Parts
    # ------------------------------------------------------------------

    def _do_parts(self, parts_file: str, mfr_id: int):
        count = 0
        if _IJSON:
            with open(parts_file, 'rb') as f:
                for part_num, part_data in ijson.kvitems(f, ''):
                    self._write_part(part_num, part_data, mfr_id)
                    count += 1
                    if count % 100_000 == 0:
                        print(f"    {count:,} parts...")
        else:
            with open(parts_file) as f:
                data = json.load(f)
            for part_num, part_data in data.items():
                self._write_part(part_num, part_data, mfr_id)
                count += 1
        print(f"    {count:,} parts total")

    def _write_part(self, part_num: str, part_data: dict, mfr_id: int):
        part_id, is_new = self._parts.get_or_create(part_num)
        if not is_new:
            return

        self._w.write('part', [
            part_id,
            part_data.get('url'),
            part_num,
            mfr_id,
            _clean_title(part_data.get('title', ''), part_num),
            None,  # category_id — not used at part level
            part_data.get('also_known_as'),
            _strip_html(part_data.get('description')),
            None,  # replaces
            part_data.get('positions'),
            part_data.get('notes'),
            part_data.get('msrp'),
            part_data.get('applications'),
            part_data.get('is_hazmat'),
        ])

        seen_imgs: set = set()
        for img_entry in part_data.get('images', []):
            for key in ('main', 'preview', 'thumb'):
                img_obj = img_entry.get(key)
                if not img_obj:
                    continue
                img_name = img_obj.get('url', '').split('/')[-1]
                if not img_name or img_name in seen_imgs:
                    continue
                img_id = self._images.get(img_name)
                if img_id is None:
                    continue
                self._w.write('part_images', [part_id, img_id, img_entry.get('caption')])
                seen_imgs.add(img_name)

    # ------------------------------------------------------------------
    # Tree
    # ------------------------------------------------------------------

    def _do_tree(self, split_tree_file: str, data_dir: str, mfr_id: int):
        with open(split_tree_file) as f:
            split = json.load(f)
        for year_str, rel_path in sorted(split.items()):
            year_file = os.path.join(data_dir, rel_path)
            if not os.path.exists(year_file):
                print(f"    Missing {year_file}, skipping year {year_str}")
                continue
            print(f"    Year {year_str}...")
            with open(year_file) as f:
                year_node = json.load(f)[year_str]
            self._do_year(year_str, year_node, mfr_id)

    def _do_year(self, year_str: str, year_node: dict, mfr_id: int):
        year_id, is_new = self._years.get_or_create(year_str)
        if is_new:
            self._w.write('year', [year_id, year_str])

        for make_key, make_node in year_node.get('makes', {}).items():
            make_id, is_new = self._makes.get_or_create(make_key)
            if is_new:
                self._w.write('make', [
                    make_id, make_node.get('ui', make_key), make_key,
                    make_node.get('start_year'), make_node.get('end_year'),
                ])

            for model_key, model_node in make_node.get('models', {}).items():
                model_map_key = f'{make_id}::{model_key}'
                model_id, is_new = self._models.get_or_create(model_map_key)
                if is_new:
                    self._w.write('model', [
                        model_id, model_node.get('ui', model_key), model_key, make_id,
                    ])

                for trim_key, trim_node in model_node.get('trims', {}).items():
                    trim_id, is_new = self._trims.get_or_create(trim_key)
                    if is_new:
                        self._w.write('trim', [
                            trim_id, trim_node.get('ui', trim_key), trim_key,
                        ])

                    for eng_key, eng_node in trim_node.get('engines', {}).items():
                        eng_id, is_new = self._engines.get_or_create(eng_key)
                        if is_new:
                            self._w.write('engine', [
                                eng_id, eng_node.get('ui', eng_key), eng_key,
                            ])

                        car_key = f'{year_id}::{make_id}::{model_id}::{trim_id}::{eng_id}'
                        car_id, is_new = self._cars.get_or_create(car_key)
                        if not is_new:
                            continue

                        self._w.write('car', [
                            car_id, year_id, make_id, model_id, trim_id, eng_id, mfr_id,
                            eng_node.get('car_id'), eng_node.get('vehicle_id'),
                            eng_node.get('page_url'),
                        ])

                        parts_set = set(eng_node.get('parts', []))
                        seen_car_parts: set = set()
                        for p_num in parts_set:
                            p_id = self._parts.get(p_num)
                            if p_id is not None and p_id not in seen_car_parts:
                                self._w.write('car_parts', [car_id, p_id])
                                seen_car_parts.add(p_id)

                        for diag_entry in eng_node.get('diagrams', []):
                            for diag in diag_entry.get('diagrams', []):
                                self._write_diagram(diag, car_id, parts_set)

    def _write_diagram(self, diag: dict, car_id: int, parts_set: set):
        diag_id = self._diagram_seq
        self._diagram_seq += 1

        img_name = diag.get('img', '')
        img_id = self._images.get(img_name) if img_name else None

        category_url = diag.get('category_link', '')
        tail = category_url.rstrip('/').split('/')[-1]
        if not tail:
            tail = category_url.rstrip('/').split('/')[-2] if '/' in category_url.rstrip('/') else ''
        cats = tail.split('--')

        category_id = None
        subcat_id   = None

        if len(cats) == 2:
            main_cat, sub_cat = cats[0].strip(), cats[1].strip()
            category_id, is_new = self._categories.get_or_create(main_cat)
            if is_new:
                self._w.write('category', [category_id, main_cat])
            sub_key = f'{category_id}::{sub_cat}'
            subcat_id, is_new = self._subcats.get_or_create(sub_key)
            if is_new:
                self._w.write('subcategory', [subcat_id, sub_cat, category_id])
        elif cats and cats[0].strip():
            main_cat = cats[0].strip()
            category_id, is_new = self._categories.get_or_create(main_cat)
            if is_new:
                self._w.write('category', [category_id, main_cat])

        self._w.write('diagram', [
            diag_id, img_id, category_id, subcat_id,
            diag.get('base_car_url'), category_url,
        ])
        self._w.write('car_diagrams', [car_id, diag_id])

        # Aggregate indices per part, combining when same part appears at multiple positions
        index_map: dict = {}
        for idx, part_nums in diag.get('parts', {}).items():
            for p_num in part_nums:
                if p_num not in parts_set:
                    continue
                p_id = self._parts.get(p_num)
                if p_id is None:
                    continue
                idx_clean = idx.strip()
                if p_id in index_map:
                    if idx_clean not in index_map[p_id].split(','):
                        index_map[p_id] += ',' + idx_clean
                else:
                    index_map[p_id] = idx_clean

        for p_id, part_index in index_map.items():
            self._w.write('diagram_parts', [diag_id, p_id, part_index])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Generate PostgreSQL COPY CSVs from scraped JSON data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
State is automatically saved to $output_dir/state.json after each manufacturer
so subsequent runs continue with non-conflicting IDs. Load each run's output
incrementally with load_csvs.py (no truncation needed).

Examples:
  python generate_csvs.py --make acura
  python generate_csvs.py --make bmw
  python generate_csvs.py --all
  python generate_csvs.py --fresh --make acura   # wipe state and start over
        """,
    )
    parser.add_argument('--output-dir', default='/tmp/parts_csvs',
                        help='Directory to write CSV files (default: /tmp/parts_csvs)')
    parser.add_argument('--data-dir',
                        help='Root directory with per-manufacturer subdirs '
                             '(overrides save_dir env var and car_configs paths)')
    parser.add_argument('--make',
                        help='Process a single manufacturer, e.g. --make gm')
    parser.add_argument('--all', action='store_true',
                        help='Process all manufacturers (ignores skip flags)')
    parser.add_argument('--fresh', action='store_true',
                        help='Delete state.json and all CSVs before starting '
                             '(also wipe the DB if reloading everything)')
    args = parser.parse_args()

    from car_configs import CarConfigs
    configs = dict(CarConfigs.configs)

    if args.data_dir:
        for name in configs:
            configs[name]['data_dir'] = os.path.join(args.data_dir, name)

    if args.make:
        target = args.make.lower()
        if target not in configs:
            print(f"Unknown manufacturer: {target}")
            print(f"Valid options: {', '.join(configs)}")
            return
        configs = {target: dict(configs[target])}
        configs[target].pop('skip', None)
    elif args.all:
        for cfg in configs.values():
            cfg.pop('skip', None)

    gen = Generator(args.output_dir)

    if args.fresh:
        print("--fresh: clearing all CSVs and state")
        gen.clear_all()

    gen.run(configs)


if __name__ == '__main__':
    main()
