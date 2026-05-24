# Phase 2b: Tarball Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingest ~10.2M cached HTML pages and ~6.1M images from extracted tarballs at `~/nfs-share/parts-direct-data/` into the webcache and imgcache services so the Phase 2 scraper can run against the cache instead of re-scraping the live site.

**Architecture:** A single CLI Python script (`ingest.py`) that walks per-make directories sequentially. For each make it reads `webcache.json` → decompresses each `.bz2` file → stores HTML to `WebCacheClient`; then reads `imgs.json` → reads each image file → stores bytes to `ImgCacheClient`. Per-make JSON state files track how many entries have been processed so runs can be resumed after interruption. All storage calls are idempotent (check before store). No Postgres writes — structured data is populated later by the Phase 2 scraper processing cache hits.

**Tech Stack:** Python 3.11+, `dwilson-cache-client==0.1.1` (WebCacheClient), `dwilson-imgcache-client==0.3.0` (ImgCacheClient), pytest, unittest.mock, bz2 stdlib

---

## Data Layout Reference

```
~/nfs-share/parts-direct-data/{make}/
    webcache.json          # {url → uuid_filename}   e.g. "https://...integra" → "2f46aac9-...56e6.bz2"
    webcache/              # .bz2 compressed HTML files (all 22 makes use .bz2; some legacy .html exist)
    imgs.json              # {filename → {url, alt, saved, uploaded}}
    images/                # image files, keyed by filename (NOT uuid)
    tree.json              # NOT used by Phase 2b
    tree_split.json        # gm/toyota only — NOT used by Phase 2b
```

**Scale:** 22 makes — acura (smallest, 179,978 webcache / 168,417 imgs) → gm (largest, 3,045,767 / 970,544). Total: 10.2M webcache, 6.1M images.

**Service ports (local dev):**
- WebCache: `http://localhost:8000` (docker-compose port)
- ImgCache: `http://localhost:8010` (docker-compose port)
- `*.scrapestack.local` addresses are Docker-internal — NOT reachable from host

---

## File Map

**Create:**
- `web_scrapers/parts_direct/tarball-ingestor/ingest.py` — CLI + all ingestion logic
- `web_scrapers/parts_direct/tarball-ingestor/requirements.txt` — Python deps
- `web_scrapers/parts_direct/tarball-ingestor/progress/.gitkeep` — dir for per-make state files (add `progress/*.json` to `.gitignore`)
- `web_scrapers/parts_direct/tarball-ingestor/tests/__init__.py` — empty
- `web_scrapers/parts_direct/tarball-ingestor/tests/test_ingest.py` — all unit tests

---

## Task 1: Scaffold and requirements

**Files:**
- Create: `web_scrapers/parts_direct/tarball-ingestor/requirements.txt`
- Create: `web_scrapers/parts_direct/tarball-ingestor/tests/__init__.py`

- [ ] **Step 1: Create requirements.txt**

```
dwilson-cache-client==0.1.1
dwilson-imgcache-client==0.3.0
pytest>=8.0
```

- [ ] **Step 2: Install dependencies**

```bash
cd web_scrapers/parts_direct/tarball-ingestor
pip install -r requirements.txt
```

Expected: packages install without errors. Verify with:
```bash
python -c "from cache_client import WebCacheClient; from imgcache_client import ImgCacheClient; print('OK')"
```

- [ ] **Step 3: Create tests/__init__.py**

Empty file:
```bash
mkdir -p web_scrapers/parts_direct/tarball-ingestor/tests
touch web_scrapers/parts_direct/tarball-ingestor/tests/__init__.py
```

- [ ] **Step 4: Verify scrape_stack is running (webcache + imgcache services)**

```bash
cd web_scrapers/scrape_stack
docker compose ps
```

Expected: `webcache` and `imgcache` containers are `Up`. If not:
```bash
docker compose up -d webcache imgcache
```

Then smoke-test reachability:
```bash
curl -s http://localhost:8000/health | head -1
curl -s http://localhost:8010/health | head -1
```

Expected: both return HTTP 200 (response body varies by service).

---

## Task 2: Progress state management

**Files:**
- Create: `web_scrapers/parts_direct/tarball-ingestor/ingest.py` (initial scaffold with progress functions only)
- Test: `web_scrapers/parts_direct/tarball-ingestor/tests/test_ingest.py`

- [ ] **Step 1: Write the failing tests**

Create `web_scrapers/parts_direct/tarball-ingestor/tests/test_ingest.py`:

```python
import bz2
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingest import load_progress, save_progress, ingest_webcache, ingest_images, MAKES


# ── Progress state ───────────────────────────────────────────────────────────

def test_load_progress_returns_zero_when_no_file(tmp_path):
    assert load_progress(tmp_path, "acura", "webcache") == 0


def test_save_and_load_progress_roundtrip(tmp_path):
    save_progress(tmp_path, "acura", "webcache", 12345)
    assert load_progress(tmp_path, "acura", "webcache") == 12345


def test_save_progress_creates_dir_if_missing(tmp_path):
    nested = tmp_path / "nested" / "dir"
    save_progress(nested, "ford", "images", 99)
    assert load_progress(nested, "ford", "images") == 99


def test_progress_files_are_per_make_and_mode(tmp_path):
    save_progress(tmp_path, "acura", "webcache", 100)
    save_progress(tmp_path, "ford", "webcache", 200)
    save_progress(tmp_path, "acura", "images", 300)
    assert load_progress(tmp_path, "acura", "webcache") == 100
    assert load_progress(tmp_path, "ford", "webcache") == 200
    assert load_progress(tmp_path, "acura", "images") == 300


def test_all_22_makes_listed():
    assert len(MAKES) == 22
    for make in ("acura", "gm", "toyota", "ford", "honda", "bmw", "vw"):
        assert make in MAKES
```

- [ ] **Step 2: Run to verify tests fail**

```bash
cd web_scrapers/parts_direct/tarball-ingestor
python -m pytest tests/test_ingest.py::test_load_progress_returns_zero_when_no_file -v
```

Expected: `ImportError: No module named 'ingest'`

- [ ] **Step 3: Create ingest.py with MAKES constant and progress functions**

Create `web_scrapers/parts_direct/tarball-ingestor/ingest.py`:

```python
import argparse
import bz2
import json
import logging
import sys
from pathlib import Path

from cache_client import WebCacheClient
from imgcache_client import ImgCacheClient

CLIENT_NAME = "parts_direct"
IMG_BUCKET = "parts-direct"
CHECKPOINT_EVERY = 1000
MAX_CACHE_AGE = 365 * 24 * 3600  # 1 year — treat anything cached as valid

MAKES = [
    "acura", "audi", "bmw", "fiat", "ford", "gm", "honda", "hyundai",
    "infiniti", "jaguar", "kia", "mazda", "mercedes", "mini", "mitsubishi",
    "nissan", "porsche", "subaru", "suzuki", "toyota", "volvo", "vw",
]

log = logging.getLogger(__name__)


def load_progress(progress_dir: Path, make: str, mode: str) -> int:
    """Return the number of entries already processed (0 = start fresh)."""
    state_file = progress_dir / f"{make}_{mode}.json"
    if state_file.exists():
        with open(state_file) as f:
            return json.load(f).get("completed", 0)
    return 0


def save_progress(progress_dir: Path, make: str, mode: str, completed: int) -> None:
    """Persist the number of completed entries so runs can resume."""
    progress_dir.mkdir(parents=True, exist_ok=True)
    state_file = progress_dir / f"{make}_{mode}.json"
    with open(state_file, "w") as f:
        json.dump({"completed": completed}, f)
```

- [ ] **Step 4: Run progress tests — all should pass**

```bash
cd web_scrapers/parts_direct/tarball-ingestor
python -m pytest tests/test_ingest.py -k "progress or makes" -v
```

Expected: 5 tests PASS.

---

## Task 3: Webcache ingestion function

**Files:**
- Modify: `web_scrapers/parts_direct/tarball-ingestor/ingest.py` (add `ingest_webcache`)
- Modify: `web_scrapers/parts_direct/tarball-ingestor/tests/test_ingest.py` (add webcache tests)

- [ ] **Step 1: Add the webcache tests**

Append to `tests/test_ingest.py`:

```python
# ── Webcache ingestion ───────────────────────────────────────────────────────

def _make_webcache_dir(tmp_path: Path, entries: dict) -> Path:
    make_dir = tmp_path / "testmake"
    wc_dir = make_dir / "webcache"
    wc_dir.mkdir(parents=True)
    (make_dir / "webcache.json").write_text(json.dumps(entries))
    return make_dir


def test_ingest_webcache_stores_new_bz2_entry(tmp_path):
    html = "<html>test page</html>"
    make_dir = _make_webcache_dir(tmp_path, {"https://example.com/page": "page.bz2"})
    (make_dir / "webcache" / "page.bz2").write_bytes(bz2.compress(html.encode()))

    web_cache = MagicMock()
    web_cache.get.return_value = None

    stats = ingest_webcache(make_dir, tmp_path / "progress", "testmake", web_cache, dry_run=False)

    web_cache.store.assert_called_once_with("https://example.com/page", html, "parts_direct")
    assert stats == {"processed": 1, "stored": 1, "skipped": 0, "errors": 0}


def test_ingest_webcache_stores_new_plain_html_entry(tmp_path):
    html = "<html>legacy file</html>"
    make_dir = _make_webcache_dir(tmp_path, {"https://example.com/page": "page.html"})
    (make_dir / "webcache" / "page.html").write_text(html, encoding="utf-8")

    web_cache = MagicMock()
    web_cache.get.return_value = None

    stats = ingest_webcache(make_dir, tmp_path / "progress", "testmake", web_cache, dry_run=False)

    web_cache.store.assert_called_once_with("https://example.com/page", html, "parts_direct")
    assert stats["stored"] == 1


def test_ingest_webcache_skips_already_cached_entry(tmp_path):
    html = "<html>already cached</html>"
    make_dir = _make_webcache_dir(tmp_path, {"https://example.com/page": "page.bz2"})
    (make_dir / "webcache" / "page.bz2").write_bytes(bz2.compress(html.encode()))

    web_cache = MagicMock()
    web_cache.get.return_value = {"content": html, "content_hash": "abc123"}

    stats = ingest_webcache(make_dir, tmp_path / "progress", "testmake", web_cache, dry_run=False)

    web_cache.store.assert_not_called()
    assert stats == {"processed": 1, "stored": 0, "skipped": 1, "errors": 0}


def test_ingest_webcache_records_error_for_missing_file(tmp_path):
    make_dir = _make_webcache_dir(tmp_path, {"https://example.com/page": "missing.bz2"})

    web_cache = MagicMock()
    stats = ingest_webcache(make_dir, tmp_path / "progress", "testmake", web_cache, dry_run=False)

    web_cache.store.assert_not_called()
    assert stats == {"processed": 1, "stored": 0, "skipped": 0, "errors": 1}


def test_ingest_webcache_dry_run_does_not_call_store(tmp_path):
    html = "<html>dry run</html>"
    make_dir = _make_webcache_dir(tmp_path, {"https://example.com/page": "page.bz2"})
    (make_dir / "webcache" / "page.bz2").write_bytes(bz2.compress(html.encode()))

    web_cache = MagicMock()
    web_cache.get.return_value = None

    stats = ingest_webcache(make_dir, tmp_path / "progress", "testmake", web_cache, dry_run=True)

    web_cache.store.assert_not_called()
    assert stats["stored"] == 1  # counted as "would store"


def test_ingest_webcache_resumes_from_saved_progress(tmp_path):
    entries = {f"https://example.com/page{i}": f"page{i}.bz2" for i in range(5)}
    make_dir = _make_webcache_dir(tmp_path, entries)
    for i in range(5):
        (make_dir / "webcache" / f"page{i}.bz2").write_bytes(
            bz2.compress(f"<html>{i}</html>".encode())
        )
    progress_dir = tmp_path / "progress"
    save_progress(progress_dir, "testmake", "webcache", 3)  # first 3 already done

    web_cache = MagicMock()
    web_cache.get.return_value = None

    ingest_webcache(make_dir, progress_dir, "testmake", web_cache, dry_run=False)

    assert web_cache.store.call_count == 2  # only entries 3 and 4


def test_ingest_webcache_saves_final_progress(tmp_path):
    html = "<html>done</html>"
    make_dir = _make_webcache_dir(tmp_path, {"https://example.com/p": "p.bz2"})
    (make_dir / "webcache" / "p.bz2").write_bytes(bz2.compress(html.encode()))

    web_cache = MagicMock()
    web_cache.get.return_value = None
    progress_dir = tmp_path / "progress"

    ingest_webcache(make_dir, progress_dir, "testmake", web_cache, dry_run=False)

    assert load_progress(progress_dir, "testmake", "webcache") == 1
```

- [ ] **Step 2: Run to verify tests fail**

```bash
cd web_scrapers/parts_direct/tarball-ingestor
python -m pytest tests/test_ingest.py -k "webcache" -v
```

Expected: `ImportError` or `AttributeError` — `ingest_webcache` does not exist yet.

- [ ] **Step 3: Add `ingest_webcache` to ingest.py**

Append to `web_scrapers/parts_direct/tarball-ingestor/ingest.py` (after `save_progress`):

```python
def ingest_webcache(
    make_dir: Path,
    progress_dir: Path,
    make: str,
    web_cache: WebCacheClient,
    dry_run: bool = False,
) -> dict:
    """Load all webcache.json entries for one make into WebCacheClient.

    Returns stats dict: {processed, stored, skipped, errors}.
    Idempotent — calls web_cache.get() before storing.
    Resumes from saved progress if interrupted.
    """
    wc_json = make_dir / "webcache.json"
    webcache_dir = make_dir / "webcache"

    with open(wc_json) as f:
        entries = list(json.load(f).items())

    total = len(entries)
    start_idx = load_progress(progress_dir, make, "webcache")
    stats = {"processed": 0, "stored": 0, "skipped": 0, "errors": 0}

    log.info("[%s] webcache: %d total, resuming from %d", make, total, start_idx)

    for i, (url, filename) in enumerate(entries):
        if i < start_idx:
            stats["processed"] += 1
            continue

        filepath = webcache_dir / filename
        if not filepath.exists():
            log.warning("[%s] missing file: %s", make, filepath.name)
            stats["errors"] += 1
            stats["processed"] += 1
            if (i + 1) % CHECKPOINT_EVERY == 0 and not dry_run:
                save_progress(progress_dir, make, "webcache", i + 1)
            continue

        if web_cache.get(url, max_age=MAX_CACHE_AGE):
            stats["skipped"] += 1
        else:
            try:
                raw = filepath.read_bytes()
                if filename.endswith(".bz2"):
                    content = bz2.decompress(raw).decode("utf-8", errors="replace")
                else:
                    content = raw.decode("utf-8", errors="replace")
                if not dry_run:
                    web_cache.store(url, content, CLIENT_NAME)
                stats["stored"] += 1
            except Exception as exc:
                log.error("[%s] webcache store failed for %s: %s", make, url, exc)
                stats["errors"] += 1

        stats["processed"] += 1

        if (i + 1) % CHECKPOINT_EVERY == 0:
            if not dry_run:
                save_progress(progress_dir, make, "webcache", i + 1)
            log.info("[%s] webcache %d/%d — stored=%d skipped=%d errors=%d",
                     make, i + 1, total, stats["stored"], stats["skipped"], stats["errors"])

    if not dry_run:
        save_progress(progress_dir, make, "webcache", total)

    log.info("[%s] webcache DONE — stored=%d skipped=%d errors=%d",
             make, stats["stored"], stats["skipped"], stats["errors"])
    return stats
```

- [ ] **Step 4: Run webcache tests — all should pass**

```bash
cd web_scrapers/parts_direct/tarball-ingestor
python -m pytest tests/test_ingest.py -k "webcache" -v
```

Expected: 7 tests PASS.

---

## Task 4: Imgcache ingestion function

**Files:**
- Modify: `web_scrapers/parts_direct/tarball-ingestor/ingest.py` (add `ingest_images`)
- Modify: `web_scrapers/parts_direct/tarball-ingestor/tests/test_ingest.py` (add image tests)

- [ ] **Step 1: Add the image tests**

Append to `tests/test_ingest.py`:

```python
# ── Imgcache ingestion ───────────────────────────────────────────────────────

def _make_images_dir(tmp_path: Path, entries: dict) -> Path:
    make_dir = tmp_path / "testmake2"
    (make_dir / "images").mkdir(parents=True)
    (make_dir / "imgs.json").write_text(json.dumps(entries))
    return make_dir


def test_ingest_images_stores_new_image(tmp_path):
    img_bytes = b"\x89PNG\r\n\x1a\n"
    entries = {"test.png": {"url": "https://cdn.example.com/test.png", "alt": "Test", "saved": True, "uploaded": True}}
    make_dir = _make_images_dir(tmp_path, entries)
    (make_dir / "images" / "test.png").write_bytes(img_bytes)

    img_cache = MagicMock()
    img_cache.lookup.return_value = None

    stats = ingest_images(make_dir, tmp_path / "progress", "testmake2", img_cache, dry_run=False)

    img_cache.store.assert_called_once_with(
        url="https://cdn.example.com/test.png",
        file_bytes=img_bytes,
        client_name="parts_direct",
        bucket="parts-direct",
        filename="test.png",
    )
    assert stats["stored"] == 1
    assert stats["skipped"] == 0
    assert stats["missing_file"] == 0
    assert stats["errors"] == 0


def test_ingest_images_skips_already_cached(tmp_path):
    img_bytes = b"\x89PNG\r\n\x1a\n"
    entries = {"test.png": {"url": "https://cdn.example.com/test.png", "alt": None, "saved": True, "uploaded": True}}
    make_dir = _make_images_dir(tmp_path, entries)
    (make_dir / "images" / "test.png").write_bytes(img_bytes)

    img_cache = MagicMock()
    img_cache.lookup.return_value = {"content_hash": "abc123"}

    stats = ingest_images(make_dir, tmp_path / "progress", "testmake2", img_cache, dry_run=False)

    img_cache.store.assert_not_called()
    assert stats["skipped"] == 1


def test_ingest_images_counts_missing_file(tmp_path):
    entries = {"missing.png": {"url": "https://cdn.example.com/missing.png", "alt": None, "saved": False, "uploaded": False}}
    make_dir = _make_images_dir(tmp_path, entries)

    img_cache = MagicMock()
    stats = ingest_images(make_dir, tmp_path / "progress", "testmake2", img_cache, dry_run=False)

    img_cache.store.assert_not_called()
    assert stats["missing_file"] == 1
    assert stats["errors"] == 0


def test_ingest_images_skips_entry_with_no_url(tmp_path):
    img_bytes = b"data"
    entries = {"test.gif": {"url": "", "alt": None, "saved": True, "uploaded": True}}
    make_dir = _make_images_dir(tmp_path, entries)
    (make_dir / "images" / "test.gif").write_bytes(img_bytes)

    img_cache = MagicMock()
    stats = ingest_images(make_dir, tmp_path / "progress", "testmake2", img_cache, dry_run=False)

    img_cache.store.assert_not_called()
    assert stats["errors"] == 1


def test_ingest_images_dry_run_does_not_call_store(tmp_path):
    img_bytes = b"\x89PNG\r\n\x1a\n"
    entries = {"test.png": {"url": "https://cdn.example.com/test.png", "alt": None, "saved": True, "uploaded": True}}
    make_dir = _make_images_dir(tmp_path, entries)
    (make_dir / "images" / "test.png").write_bytes(img_bytes)

    img_cache = MagicMock()
    img_cache.lookup.return_value = None

    stats = ingest_images(make_dir, tmp_path / "progress", "testmake2", img_cache, dry_run=True)

    img_cache.store.assert_not_called()
    assert stats["stored"] == 1


def test_ingest_images_saves_final_progress(tmp_path):
    img_bytes = b"data"
    entries = {"img.gif": {"url": "https://cdn.example.com/img.gif", "alt": None, "saved": True, "uploaded": True}}
    make_dir = _make_images_dir(tmp_path, entries)
    (make_dir / "images" / "img.gif").write_bytes(img_bytes)

    img_cache = MagicMock()
    img_cache.lookup.return_value = None
    progress_dir = tmp_path / "progress"

    ingest_images(make_dir, progress_dir, "testmake2", img_cache, dry_run=False)

    assert load_progress(progress_dir, "testmake2", "images") == 1


def test_ingest_images_resumes_from_saved_progress(tmp_path):
    entries = {f"img{i}.png": {"url": f"https://cdn.example.com/img{i}.png", "alt": None, "saved": True, "uploaded": True}
               for i in range(5)}
    make_dir = _make_images_dir(tmp_path, entries)
    for i in range(5):
        (make_dir / "images" / f"img{i}.png").write_bytes(b"data")

    progress_dir = tmp_path / "progress"
    save_progress(progress_dir, "testmake2", "images", 3)

    img_cache = MagicMock()
    img_cache.lookup.return_value = None

    ingest_images(make_dir, progress_dir, "testmake2", img_cache, dry_run=False)

    assert img_cache.store.call_count == 2  # only entries 3 and 4
```

- [ ] **Step 2: Run to verify tests fail**

```bash
cd web_scrapers/parts_direct/tarball-ingestor
python -m pytest tests/test_ingest.py -k "images" -v
```

Expected: `ImportError` or `AttributeError` — `ingest_images` does not exist yet.

- [ ] **Step 3: Add `ingest_images` to ingest.py**

Append to `web_scrapers/parts_direct/tarball-ingestor/ingest.py` (after `ingest_webcache`):

```python
def ingest_images(
    make_dir: Path,
    progress_dir: Path,
    make: str,
    img_cache: ImgCacheClient,
    dry_run: bool = False,
) -> dict:
    """Load all imgs.json entries for one make into ImgCacheClient.

    Returns stats dict: {processed, stored, skipped, errors, missing_file}.
    Idempotent — calls img_cache.lookup() before storing.
    Skips entries where the image file doesn't exist on disk (logs count as missing_file).
    Resumes from saved progress if interrupted.
    """
    imgs_json = make_dir / "imgs.json"
    images_dir = make_dir / "images"

    with open(imgs_json) as f:
        entries = list(json.load(f).items())

    total = len(entries)
    start_idx = load_progress(progress_dir, make, "images")
    stats = {"processed": 0, "stored": 0, "skipped": 0, "errors": 0, "missing_file": 0}

    log.info("[%s] images: %d total, resuming from %d", make, total, start_idx)

    for i, (filename, meta) in enumerate(entries):
        if i < start_idx:
            stats["processed"] += 1
            continue

        url = meta.get("url", "")
        if not url:
            stats["errors"] += 1
            stats["processed"] += 1
            continue

        filepath = images_dir / filename
        if not filepath.exists():
            stats["missing_file"] += 1
            stats["processed"] += 1
            if (i + 1) % CHECKPOINT_EVERY == 0 and not dry_run:
                save_progress(progress_dir, make, "images", i + 1)
            continue

        if img_cache.lookup(url, bucket=IMG_BUCKET):
            stats["skipped"] += 1
        else:
            try:
                file_bytes = filepath.read_bytes()
                if not dry_run:
                    img_cache.store(
                        url=url,
                        file_bytes=file_bytes,
                        client_name=CLIENT_NAME,
                        bucket=IMG_BUCKET,
                        filename=filename,
                    )
                stats["stored"] += 1
            except Exception as exc:
                log.error("[%s] imgcache store failed for %s: %s", make, url, exc)
                stats["errors"] += 1

        stats["processed"] += 1

        if (i + 1) % CHECKPOINT_EVERY == 0:
            if not dry_run:
                save_progress(progress_dir, make, "images", i + 1)
            log.info("[%s] images %d/%d — stored=%d skipped=%d missing=%d errors=%d",
                     make, i + 1, total, stats["stored"], stats["skipped"],
                     stats["missing_file"], stats["errors"])

    if not dry_run:
        save_progress(progress_dir, make, "images", total)

    log.info("[%s] images DONE — stored=%d skipped=%d missing=%d errors=%d",
             make, stats["stored"], stats["skipped"], stats["missing_file"], stats["errors"])
    return stats
```

- [ ] **Step 4: Run image tests — all should pass**

```bash
cd web_scrapers/parts_direct/tarball-ingestor
python -m pytest tests/test_ingest.py -k "images" -v
```

Expected: 7 tests PASS.

- [ ] **Step 5: Run the full unit test suite**

```bash
cd web_scrapers/parts_direct/tarball-ingestor
python -m pytest tests/test_ingest.py -v
```

Expected: all tests PASS (progress + webcache + images = ~19 tests).

---

## Task 5: CLI and main orchestration

**Files:**
- Modify: `web_scrapers/parts_direct/tarball-ingestor/ingest.py` (add `main()` and CLI)

The CLI is simple wiring — no new test coverage needed beyond import smoke test.

- [ ] **Step 1: Add main() and argparse to ingest.py**

Append to `web_scrapers/parts_direct/tarball-ingestor/ingest.py`:

```python
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest parts-direct tarball data into webcache/imgcache services"
    )
    parser.add_argument(
        "--base-dir",
        default=str(Path.home() / "nfs-share" / "parts-direct-data"),
        help="Base directory containing per-make data (default: ~/nfs-share/parts-direct-data)",
    )
    parser.add_argument(
        "--make",
        help="Process only this make (e.g. acura). Omit to process all 22 makes.",
    )
    parser.add_argument(
        "--webcache-only",
        action="store_true",
        help="Only ingest webcache HTML entries (skip images)",
    )
    parser.add_argument(
        "--images-only",
        action="store_true",
        help="Only ingest image entries (skip webcache HTML)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse data and count what would be stored, but do not call store()",
    )
    parser.add_argument(
        "--webcache-url",
        default="http://localhost:8000",
        help="WebCache service URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--imgcache-url",
        default="http://localhost:8010",
        help="ImgCache service URL (default: http://localhost:8010)",
    )
    parser.add_argument(
        "--progress-dir",
        default=str(Path(__file__).parent / "progress"),
        help="Directory for per-make progress state files",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    base_dir = Path(args.base_dir)
    progress_dir = Path(args.progress_dir)
    makes = [args.make] if args.make else MAKES

    do_webcache = not args.images_only
    do_images = not args.webcache_only

    with WebCacheClient(args.webcache_url) as web_cache, \
         ImgCacheClient(args.imgcache_url) as img_cache:

        for make in makes:
            make_dir = base_dir / make
            if not make_dir.is_dir():
                log.warning("Make directory not found: %s — skipping", make_dir)
                continue

            log.info("=== Processing make: %s ===", make)

            if do_webcache:
                wc_json = make_dir / "webcache.json"
                if wc_json.exists():
                    ingest_webcache(make_dir, progress_dir, make, web_cache, dry_run=args.dry_run)
                else:
                    log.warning("[%s] no webcache.json found — skipping webcache", make)

            if do_images:
                imgs_json = make_dir / "imgs.json"
                if imgs_json.exists():
                    ingest_images(make_dir, progress_dir, make, img_cache, dry_run=args.dry_run)
                else:
                    log.warning("[%s] no imgs.json found — skipping images", make)

    log.info("Ingestion complete.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the CLI imports and --help work**

```bash
cd web_scrapers/parts_direct/tarball-ingestor
python ingest.py --help
```

Expected output (excerpt):
```
usage: ingest.py [-h] [--base-dir BASE_DIR] [--make MAKE] [--webcache-only]
                 [--images-only] [--dry-run] [--webcache-url WEBCACHE_URL]
                 [--imgcache-url IMGCACHE_URL] [--progress-dir PROGRESS_DIR]
```

No errors or tracebacks.

- [ ] **Step 3: Create the progress directory placeholder**

```bash
mkdir -p web_scrapers/parts_direct/tarball-ingestor/progress
touch web_scrapers/parts_direct/tarball-ingestor/progress/.gitkeep
```

Add to `.gitignore` at the repo root (or in the tarball-ingestor directory):
```
progress/*.json
```

---

## Task 6: Dry-run smoke test against real data

This task verifies the script can read and parse real data without crashing. It does NOT store anything to the services (uses `--dry-run`). Run this before attempting any real ingestion.

- [ ] **Step 1: Verify the data directory is mounted**

```bash
ls ~/nfs-share/parts-direct-data/ | head -5
```

Expected: directories for the 22 makes (`acura`, `audi`, `bmw`, etc.) are listed.

- [ ] **Step 2: Dry-run acura webcache (179,978 entries)**

```bash
cd web_scrapers/parts_direct/tarball-ingestor
python ingest.py \
  --make acura \
  --webcache-only \
  --dry-run \
  --webcache-url http://localhost:8000
```

Expected: completes without error. Final log line should look like:
```
HH:MM:SS INFO [acura] webcache DONE — stored=179978 skipped=0 errors=N
```

Where `N` is the number of missing files (may be zero or small). If `errors` is more than 1% of total, investigate before proceeding.

- [ ] **Step 3: Dry-run acura images (168,417 entries)**

```bash
cd web_scrapers/parts_direct/tarball-ingestor
python ingest.py \
  --make acura \
  --images-only \
  --dry-run \
  --imgcache-url http://localhost:8010
```

Expected: completes without error. Final log line:
```
HH:MM:SS INFO [acura] images DONE — stored=N skipped=0 missing=M errors=0
```

Where `M` (missing files) may be non-zero — some `imgs.json` entries may not have files on disk if the original images failed to save. That's expected.

- [ ] **Step 4: Real-store first 50 acura webcache entries (manual subset test)**

This uses a trick: write a temporary progress file that pretends 50 entries are "done from the other side" — i.e., set `completed` to the total minus 50 so only the last 50 run. First check the acura total:

```bash
python3 -c "import json; d=json.load(open('/home/daniel/nfs-share/parts-direct-data/acura/webcache.json')); print(len(d))"
```

Expected: `179978`

```bash
# Set progress so only entries 179928..179977 (last 50) will be processed
python3 -c "
import json
from pathlib import Path
d = {'completed': 179928}
p = Path('web_scrapers/parts_direct/tarball-ingestor/progress')
p.mkdir(exist_ok=True)
(p / 'acura_webcache.json').write_text(json.dumps(d))
print('Progress set to 179928')
"
```

Now run real store on those 50 entries:

```bash
cd web_scrapers/parts_direct/tarball-ingestor
python ingest.py \
  --make acura \
  --webcache-only \
  --webcache-url http://localhost:8000
```

Expected: 50 entries stored. Log should show `stored=50 skipped=0 errors=0`.

- [ ] **Step 5: Verify those 50 entries appear in webcache**

Pick one of the last 50 URLs from acura's webcache.json:

```bash
python3 -c "
import json
entries = list(json.load(open('/home/daniel/nfs-share/parts-direct-data/acura/webcache.json')).items())
url = entries[179977][0]
print(url)
"
```

Then verify it's retrievable from the service:

```bash
URL=$(python3 -c "import json; e=list(json.load(open('/home/daniel/nfs-share/parts-direct-data/acura/webcache.json')).items()); print(e[179977][0])")
curl -s "http://localhost:8000/get?url=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$URL', safe=''))")" | python3 -c "import sys,json; d=json.load(sys.stdin); print('content_hash:', d.get('content_hash')); print('content_len:', len(d.get('content','')))"
```

Expected: prints a `content_hash` and a non-zero `content_len`.

- [ ] **Step 6: Reset acura progress and do a second run (idempotency check)**

```bash
rm web_scrapers/parts_direct/tarball-ingestor/progress/acura_webcache.json
```

Run again with `--dry-run` but this time the 50 entries we stored should show as `skipped` (they're already cached):

```bash
cd web_scrapers/parts_direct/tarball-ingestor
python ingest.py \
  --make acura \
  --webcache-only \
  --dry-run \
  --webcache-url http://localhost:8000 2>&1 | tail -5
```

Expected final line: `stored=N skipped=50 errors=M` — the 50 previously-stored entries now appear as `skipped`.

---

## Task 7: Integration test for CI

A fast automated integration test that stores 3 real entries (1 webcache + 1 image + 1 already-cached) against live services. Requires services running at localhost:8000/8010. Skips if services are unreachable.

**Files:**
- Create: `web_scrapers/parts_direct/tarball-ingestor/tests/test_integration.py`

- [ ] **Step 1: Write the integration test**

Create `web_scrapers/parts_direct/tarball-ingestor/tests/test_integration.py`:

```python
"""
Integration tests for tarball ingestor against real webcache/imgcache services.

Requires:
  - scrape_stack webcache running at http://localhost:8000
  - scrape_stack imgcache running at http://localhost:8010
  - ~/nfs-share/parts-direct-data/acura/ data present

Run:
  pytest tests/test_integration.py -v
"""
import bz2
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ACURA_DIR = Path.home() / "nfs-share" / "parts-direct-data" / "acura"
WEBCACHE_URL = "http://localhost:8000"
IMGCACHE_URL = "http://localhost:8010"


def _services_reachable() -> bool:
    try:
        import httpx
        r1 = httpx.get(f"{WEBCACHE_URL}/health", timeout=3)
        r2 = httpx.get(f"{IMGCACHE_URL}/health", timeout=3)
        return r1.status_code < 500 and r2.status_code < 500
    except Exception:
        return False


def _data_present() -> bool:
    return ACURA_DIR.is_dir() and (ACURA_DIR / "webcache.json").exists()


requires_services = pytest.mark.skipif(
    not _services_reachable(),
    reason="webcache/imgcache services not reachable at localhost:8000/8010"
)
requires_data = pytest.mark.skipif(
    not _data_present(),
    reason="~/nfs-share/parts-direct-data/acura/ not present"
)


@requires_services
@requires_data
def test_ingest_webcache_real_single_entry(tmp_path):
    """Store the first acura webcache entry and verify it's retrievable."""
    from cache_client import WebCacheClient
    from ingest import ingest_webcache

    with open(ACURA_DIR / "webcache.json") as f:
        first_url, first_filename = next(iter(json.load(f).items()))

    # Only run 1 entry by using a fake make_dir with a single-entry webcache.json
    fake_make_dir = tmp_path / "acura_single"
    fake_wc_dir = fake_make_dir / "webcache"
    fake_wc_dir.mkdir(parents=True)
    (fake_make_dir / "webcache.json").write_text(json.dumps({first_url: first_filename}))

    real_file = ACURA_DIR / "webcache" / first_filename
    if not real_file.exists():
        pytest.skip(f"File not present: {real_file}")

    (fake_wc_dir / first_filename).write_bytes(real_file.read_bytes())

    progress_dir = tmp_path / "progress"

    with WebCacheClient(WEBCACHE_URL) as web_cache:
        # Delete if already cached so test is deterministic
        existing = web_cache.get(first_url, max_age=365 * 24 * 3600)
        if existing:
            web_cache.delete(existing["content_hash"])

        stats = ingest_webcache(fake_make_dir, progress_dir, "acura_single", web_cache, dry_run=False)

    assert stats["stored"] == 1, f"Expected 1 stored, got: {stats}"

    # Verify it's now in the cache
    with WebCacheClient(WEBCACHE_URL) as web_cache:
        entry = web_cache.get(first_url, max_age=365 * 24 * 3600)
    assert entry is not None, "Entry not found in webcache after store"
    assert len(entry.get("content", "")) > 100


@requires_services
@requires_data
def test_ingest_images_real_single_entry(tmp_path):
    """Store the first acura image and verify lookup returns content_hash."""
    from imgcache_client import ImgCacheClient
    from ingest import ingest_images

    with open(ACURA_DIR / "imgs.json") as f:
        imgs = json.load(f)

    # Find first entry that has a file on disk
    first_filename = first_meta = None
    for fname, meta in imgs.items():
        if meta.get("url") and (ACURA_DIR / "images" / fname).exists():
            first_filename = fname
            first_meta = meta
            break

    if first_filename is None:
        pytest.skip("No acura image files found on disk")

    fake_make_dir = tmp_path / "acura_single_img"
    fake_images_dir = fake_make_dir / "images"
    fake_images_dir.mkdir(parents=True)
    (fake_make_dir / "imgs.json").write_text(json.dumps({first_filename: first_meta}))
    (fake_images_dir / first_filename).write_bytes((ACURA_DIR / "images" / first_filename).read_bytes())

    progress_dir = tmp_path / "progress"
    url = first_meta["url"]

    with ImgCacheClient(IMGCACHE_URL) as img_cache:
        stats = ingest_images(fake_make_dir, progress_dir, "acura_single_img", img_cache, dry_run=False)

    assert stats["stored"] == 1 or stats["skipped"] == 1, f"Unexpected stats: {stats}"

    with ImgCacheClient(IMGCACHE_URL) as img_cache:
        result = img_cache.lookup(url, bucket="parts-direct")
    assert result is not None, "Image not found in imgcache after store"
```

- [ ] **Step 2: Run the integration tests**

```bash
cd web_scrapers/parts_direct/tarball-ingestor
pip install httpx  # needed for reachability check in test
python -m pytest tests/test_integration.py -v
```

Expected: both tests PASS (or SKIP if services/data not available).

- [ ] **Step 3: Run the full test suite one final time**

```bash
cd web_scrapers/parts_direct/tarball-ingestor
python -m pytest tests/ -v
```

Expected: all unit tests PASS; integration tests PASS or SKIP.

---

## Self-Review

### 1. Spec coverage

| Requirement | Task |
|---|---|
| Walk per-make directories for all 22 makes | Task 5 (`main()` iterates `MAKES`) |
| Read `webcache.json` → decompress `.bz2` → store to WebCacheClient | Task 3 (`ingest_webcache`) |
| Read `imgs.json` → read image file → store to ImgCacheClient | Task 4 (`ingest_images`) |
| Idempotent: check before storing | Task 3 (`web_cache.get()`), Task 4 (`img_cache.lookup()`) |
| Resumable with per-make checkpointing every 1000 entries | Tasks 2+3+4 (progress files) |
| Dry-run mode | Tasks 3, 4, 5 (`dry_run` param) |
| CLI: `--make`, `--webcache-only`, `--images-only`, `--dry-run`, `--base-dir` | Task 5 (argparse) |
| Progress reporting every 1000 entries | Tasks 3+4 (log.info every `CHECKPOINT_EVERY`) |
| Errors logged and skipped (don't abort whole make) | Tasks 3+4 (try/except, log.error, stats["errors"]) |
| Missing files counted separately from errors | Task 4 (`stats["missing_file"]`) |
| Does NOT write to Postgres | All tasks — no DB imports anywhere |
| Uses localhost:8000 / localhost:8010 (not scrapestack.local) | Task 5 defaults, Task 6 commands |
| No git commits | All tasks — no commit steps |

### 2. Placeholder scan

No TBDs, TODOs, "handle edge cases", or "similar to Task N" patterns found.

### 3. Type consistency

- `ingest_webcache` and `ingest_images` both accept `(make_dir: Path, progress_dir: Path, make: str, client, dry_run: bool) -> dict`
- `load_progress(progress_dir, make, mode) -> int` and `save_progress(progress_dir, make, mode, completed) -> None` — consistent across all call sites
- `stats` dict keys: webcache has `{processed, stored, skipped, errors}`, images has `{processed, stored, skipped, errors, missing_file}` — the extra `missing_file` key in images is intentional and documented
- `CLIENT_NAME = "parts_direct"` and `IMG_BUCKET = "parts-direct"` used consistently in both store calls
