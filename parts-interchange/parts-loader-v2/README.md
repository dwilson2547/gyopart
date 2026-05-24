# Parts Interchange — Bulk Loader v2

High-speed bulk loader for the parts interchange database. Converts scraped
JSON data into PostgreSQL via `COPY FROM STDIN` instead of ORM row-by-row
inserts — loads that previously took days complete in minutes.

---

## How it works

**Two-phase pipeline:**

```
imgs.json  ─┐
parts.json ─┼─► generate_csvs.py ─► *.csv files ─► load_csvs.py ─► PostgreSQL
tree.json  ─┘       (Phase 1)                          (Phase 2)
```

**Phase 1 — Generate:** Streams each JSON file (using `ijson` for large files)
and writes one CSV per database table. IDs are assigned sequentially by the
script. A `state.json` file is saved after each manufacturer so that subsequent
runs continue with non-conflicting IDs.

**Phase 2 — Load:** Streams each CSV into PostgreSQL using `COPY FROM STDIN`.
FK constraint triggers are disabled for the duration of the load, then
re-enabled and sequences are reset.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Docker + Docker Compose | For the PostgreSQL container |
| Conda (py39 environment) | `ijson` and `psycopg2-binary` must be installed |
| Unpacked scraper data | One directory per manufacturer under the data root |

### Install Python dependencies

```bash
./run_local.sh setup
```

---

## Quickstart

### 1. Start PostgreSQL

```bash
cd /path/to/parts_interchange/db
docker compose up -d
```

The database starts on `localhost:5432` with:
- User: `parts_user`
- Password: `parts_pass`
- Database: `parts_interchange`

Override any of these with environment variables (see [Configuration](#configuration)).

### 2. Load your first manufacturer

```bash
cd parts-loader-v2

MAKE=acura ./run_local.sh generate        # Phase 1: JSON → CSV
./run_local.sh load --init-schema         # Phase 2: CSV → DB (--init-schema creates tables)
```

### 3. Add more manufacturers

```bash
MAKE=bmw ./run_local.sh generate          # state.json carries IDs forward automatically
./run_local.sh load                       # no --init-schema needed after first load
```

Repeat for each manufacturer. Each `generate` run produces only the rows that
don't yet exist in the database. Each `load` run appends them incrementally.

---

## Commands

All commands are run from the `parts-loader-v2` directory.

```
./run_local.sh <command> [args]
```

| Command | Description |
|---|---|
| `setup` | Install Python dependencies into the conda env |
| `generate` | Phase 1: stream JSON files → CSV |
| `load` | Phase 2: COPY CSVs into PostgreSQL |
| `all` | `generate` then `load --init-schema` in one step |
| `init-state` | Bootstrap `state.json` from an existing DB (see [Recovery](#recovery)) |
| `reset-db` | Drop all tables — pair with `generate --fresh` |
| `fresh` | Full restart: `reset-db` + `generate --fresh` + `load --init-schema` |

### `generate` flags

| Flag | Description |
|---|---|
| `--make <name>` | Process a single manufacturer (e.g. `--make gm`) |
| `--all` | Process all manufacturers, ignoring `skip` flags |
| `--fresh` | Wipe `state.json` and all CSVs before starting. **Must be paired with `reset-db`** — see [Full restart](#full-restart). |

### `load` flags

| Flag | Description |
|---|---|
| `--init-schema` | Run `schema.sql` before loading (creates tables). Safe to re-run. |
| `--reset-db` | Drop and recreate the `public` schema (wipes all data) |

---

## Workflows

### Adding a manufacturer

```bash
MAKE=toyota ./run_local.sh generate
./run_local.sh load
```

### Full restart (wipe everything and reload)

Use this when you need to reload from scratch — e.g. after schema changes.

```bash
MAKE=acura ./run_local.sh fresh
# then add more:
MAKE=bmw ./run_local.sh generate && ./run_local.sh load
```

Or to reload all non-skipped manufacturers in one shot, temporarily remove
the `skip: True` flags in `src/car_configs.py`, then:

```bash
./run_local.sh fresh --all
```

> **Important:** `generate --fresh` and `reset-db` must always be used together.
> Running `--fresh` on the generate side wipes the ID state, so IDs restart
> from 1. If the DB still has old data, the load will fail with PK conflicts.
> The `fresh` command handles both sides atomically.

### Processing large manufacturers (e.g. GM)

GM's dataset is large enough that the tree split step matters. `generate_csvs.py`
handles this automatically — it splits `tree.json` into per-year files under a
`years/` subdirectory on first run and reads them one at a time on subsequent
runs. The split files are left in place so you don't pay that cost again.

```bash
MAKE=gm ./run_local.sh generate    # will take a while; low RAM usage
./run_local.sh load
```

---

## Recovery

### DB has data but `state.json` is missing

This happens if the CSV directory was wiped or the state file was lost.
`init-state` reconstructs `state.json` by reading the current max IDs and
entity maps directly from the database.

```bash
./run_local.sh init-state          # reads DB → writes state.json
MAKE=<next_manufacturer> ./run_local.sh generate
./run_local.sh load
```

### Load failed partway through

If `load_csvs.py` fails on a particular table, any tables already committed
before the failure are in the DB. Tables after the failure point are not.
The safest recovery is a full restart:

```bash
MAKE=<same_manufacturer> ./run_local.sh fresh
```

---

## Configuration

Environment variables control both the data paths and the database connection.
All have sensible defaults for local development.

| Variable | Default | Description |
|---|---|---|
| `MAKE` | *(none)* | Manufacturer to process (e.g. `MAKE=gm`) |
| `SAVE_DIR` | `/mnt/z/parts_direct_recovery` | Root of unpacked scraper data |
| `CSV_DIR` | `~/documents/workspace/parts_interchange/csvs` | CSV staging directory |
| `CONDA_ENV` | `py39` | Conda environment name |
| `DB_HOST` | `localhost` | PostgreSQL host |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_USER` | `parts_user` | PostgreSQL user |
| `DB_PASS` | `parts_pass` | PostgreSQL password |
| `DB_NAME` | `parts_interchange` | Database name |

Example with overrides:

```bash
DB_HOST=192.168.1.50 CSV_DIR=/data/csvs MAKE=honda ./run_local.sh generate
```

---

## Data layout

The scraper produces three files per manufacturer under `$SAVE_DIR/<make>/`:

| File | Contents |
|---|---|
| `imgs.json` | `{ "filename.jpg": { url, alt, saved, uploaded } }` |
| `parts.json` | `{ "PART-NUM": { title, url, images, description, … } }` |
| `tree.json` | Nested hierarchy: year → make → model → trim → engine → { parts, diagrams } |
| `tree_split.json` | Created automatically — index of per-year files |
| `years/<year>.json` | Created automatically — one file per model year |

---

## State file

`$CSV_DIR/state.json` is the persistence layer between generate runs. It stores:

- ID maps for all **shared** tables (year, make, model, trim, engine, category,
  subcategory) so the same entity gets the same ID across manufacturers
- Sequence offsets for **per-manufacturer** tables (image, part, car, diagram)
  so IDs never collide even though each manufacturer's maps are reset
- A `processed` list of manufacturers that have been successfully generated,
  so re-running the script skips them rather than duplicating rows

The state file is written after each manufacturer completes. It is safe to
delete (use `--fresh` or `init-state` to recover), but should not be edited
manually.

---

## Database schema

Tables and their FK dependencies (load order):

```
manufacturer
year  make  trim  engine  category
  └── model          └── subcategory
  └── image (→ manufacturer)
  └── part  (→ manufacturer)
       └── car (→ year, make, model, trim, engine, manufacturer)
       └── diagram (→ image, category, subcategory)
            └── part_images  (part ↔ image)
            └── diagram_parts (diagram ↔ part)
            └── car_parts     (car ↔ part)
            └── car_diagrams  (car ↔ diagram)
```

The full DDL is in `src/schema.sql`. It uses `CREATE TABLE IF NOT EXISTS`
throughout so it is safe to re-run against an existing database.
