import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from versioned_browser_cache import WEBCACHE_METADATA_FILE, VersionedBrowserCache


def test_legacy_cache_without_metadata_is_not_usable(tmp_path):
    data_dir = tmp_path / "ford"
    cache_dir = data_dir / "webcache"
    cache_dir.mkdir(parents=True)

    url = "https://example.com/path"
    file_name = "d18f1cc4-1f65-56d7-9f6a-15d45f2d4cd7.bz2"
    (data_dir / "webcache.json").write_text(json.dumps({url: file_name}))
    (cache_dir / file_name).write_bytes(b"BZh91AY&SY")

    cache = VersionedBrowserCache("ford", str(data_dir), cache_version=2)

    assert cache.page_exists_in_cache(url) is True
    assert cache.is_cache_entry_usable(url, max_age_days=30, min_version=2) is False


def test_cache_save_persists_metadata(tmp_path):
    data_dir = tmp_path / "ford"
    data_dir.mkdir(parents=True)

    cache = VersionedBrowserCache("ford", str(data_dir), cache_version=3)
    url = "https://example.com/path?foo=bar"
    cache.add_to_cache(url, "<html>ok</html>", lookup_date="2026-05-03T00:00:00Z")
    cache.save()

    metadata_path = data_dir / WEBCACHE_METADATA_FILE
    metadata = json.loads(metadata_path.read_text())
    assert metadata["https://example.com/path"]["version"] == 3
    assert metadata["https://example.com/path"]["lookup_date"] == "2026-05-03T00:00:00Z"
