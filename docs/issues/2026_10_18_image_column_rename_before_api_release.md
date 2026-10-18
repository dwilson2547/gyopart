# Renaming image.imgcache_hash before releasing gyopart-api made every diagram request fail with UndefinedColumn

**Date:** 2026-10-18  
**Component:** `parts-interchange/db/alembic/versions/0003_image_content_hash.py`; `gyopart-api/src/routers/diagrams.py` — `get_diagram` (via `parts_interchange_common.models.Image`)  
**Severity:** High — prod diagram pages returned 500 while it lasted (a few minutes, ending at the 01:22 UTC rollback; ⚠ start time unrecorded); dev was down for longer, from when 0003 was applied there on 2026-10-17 until the API is rebuilt

---

## Observed symptom

`GET https://gyopart.danwils.com/v1/diagrams/1` returned `500 Internal Server Error` right after migration 0003 ran on
prod. gyopart-api logged:

```
sqlalchemy.exc.ProgrammingError: (psycopg2.errors.UndefinedColumn) column image.imgcache_hash does not exist
[SQL: SELECT image.id AS image_id, image.name AS image_name, image.bucket_path ... image.imgcache_hash ...
```

The only failing requests in prod's log were the test request (01:21:27 UTC); no other traffic hit a diagram page in
that window. Dev's `api.gyopart-dev.local/v1/diagrams/1` failed the same way.

---

## Root cause

### The schema changed before the code that reads it

0003 renames `image.imgcache_hash` to `content_hash`. The model with the new name is in
`dwilson-parts-interchange-common` 0.4.0, which was bumped in the repo but not yet published. gyopart-api installs
the package unpinned from PyPI, so its image has 0.3.0, which still maps `imgcache_hash`.

### The ORM selects every mapped column

`db.get(Image, diagram.image_id)` builds a `SELECT` listing every column on the model, so a column that exists in the
model but not in the table fails the whole query, even though the API never reads that column.

The migration was checked only against the writers (the parts-direct updaters: v2 on prod doesn't touch the column;
the old single-threaded scraper that does isn't deployed), not against the readers.

---

## Troubleshooting steps taken

1. **Checked the scrapers after migrating** — `git grep imgcache_hash origin/main` found it only in the undeployed
   single-threaded scraper; prod runs the v2 updater. Ruled out as the breakage.
2. **Checked the package's consumers** — `gyopart-api/requirements.txt` lists the package unpinned, and
   `src/models.py` imports `Image` from it. Ruled in.
3. **Requested a diagram from prod** — 500 with `UndefinedColumn image.imgcache_hash`. Confirmed.
4. **Rolled 0003 back on prod** (index dropped, column renamed back, `alembic_version` = `0002_scrape_keys`) — the
   same request returned 200.

---

## Fix

### Release order for a column rename

1. Publish the shared package with the new model (0.4.0).
2. Rebuild and push gyopart-api (it pulls the new package).
3. Run the migration and restart gyopart-api right after it, in that order, per environment.

Dev: 0003 is already applied, so steps 1–2 and a restart fix it.

---

## Files changed

- none (prod schema rolled back to 0002; the release order above is the fix)

## Resolution

Done in that order on 2026-10-18: common 0.4.0 on PyPI; gyopart-api 3.0.8 (`v3.0.8`, `a516879`; the requirement is
now pinned `>=0.4.0` so a cached 0.3.0 layer can't be reused); dev on 3.0.8 (200 again); prod `values.yaml` 3.0.8
(`d072e92`), with the rename run 1 s after the new pod was ready and `ix_image_content_hash` built `CONCURRENTLY`
afterwards so the table was never locked for the build. No `UndefinedColumn` errors after the rollout.
