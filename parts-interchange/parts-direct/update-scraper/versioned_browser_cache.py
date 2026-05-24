import bz2
import json
import os
import shutil
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional


WEBCACHE_METADATA_FILE = "webcache_metadata.json"
WEBCACHE_BACKUPS_DIR = "save_file_backups"
WEBCACHE_DIR = "webcache"
WEBCACHE_FILE = "webcache.json"


class VersionedBrowserCache:
    cache: Dict[str, str] = {}

    def __init__(self, config_name: str, base_dir: str, cache_version: int, secondary_lookup_dir: str = None):
        self.config_name = config_name
        self.base_dir = base_dir
        self.cache_version = cache_version
        self.data_dir = os.path.join(base_dir, WEBCACHE_DIR)
        self.webcache_file = os.path.join(base_dir, WEBCACHE_FILE)
        self.metadata_file = os.path.join(base_dir, WEBCACHE_METADATA_FILE)
        self.backup_dir = os.path.join(base_dir, WEBCACHE_BACKUPS_DIR)
        self.backup_webcache_file = os.path.join(self.backup_dir, WEBCACHE_FILE)
        self.backup_metadata_file = os.path.join(self.backup_dir, WEBCACHE_METADATA_FILE)
        self.secondary_lookup_dir = secondary_lookup_dir if secondary_lookup_dir else ""

        if not os.path.exists(self.data_dir):
            os.mkdir(self.data_dir)
        if not os.path.exists(self.backup_dir):
            os.mkdir(self.backup_dir)

        self.cache = self._load_cache()
        self.metadata = self._load_metadata()

    def add_to_cache(self, page_url: str, page_text: str, lookup_date: Optional[str] = None):
        clean_url = self.get_clean_url(page_url)
        file_name = str(uuid.uuid5(uuid.NAMESPACE_URL, clean_url)) + ".bz2"

        with bz2.open(os.path.join(self.data_dir, file_name), "wt") as file_handle:
            file_handle.write(page_text)

        self.cache[clean_url] = file_name
        self.metadata[clean_url] = {
            "version": self.cache_version,
            "lookup_date": lookup_date or self._utc_now(),
        }

    def remove_from_cache(self, page_url: str):
        clean_url = self.get_clean_url(page_url)
        file_name = self.cache.get(clean_url)
        if file_name:
            path = os.path.join(self.data_dir, file_name)
            if os.path.exists(path):
                os.remove(path)
        self.cache.pop(clean_url, None)
        self.metadata.pop(clean_url, None)

    def save(self):
        with open(self.webcache_file, "w") as file_handle:
            file_handle.write(json.dumps(self.cache))

        with open(self.metadata_file, "w") as file_handle:
            file_handle.write(json.dumps(self.metadata))

        shutil.copyfile(self.webcache_file, self.backup_webcache_file)
        shutil.copyfile(self.metadata_file, self.backup_metadata_file)

    def bucket_save(self, bucket_util):
        bucket_util.dump_json_to_bucket("part-images", self.config_name, WEBCACHE_FILE, self.cache)
        bucket_util.dump_json_to_bucket("part-images", self.config_name, WEBCACHE_METADATA_FILE, self.metadata)

    def page_exists_in_cache(self, url: str) -> bool:
        clean_url = self.get_clean_url(url)
        file_name = self.cache.get(clean_url)
        if file_name:
            if os.path.exists(os.path.join(self.data_dir, file_name)):
                return True
            if self.secondary_lookup_dir and os.path.exists(os.path.join(self.secondary_lookup_dir, file_name)):
                return True
            return False

        legacy_file_name = str(uuid.uuid5(uuid.NAMESPACE_URL, clean_url))
        html_path = os.path.join(self.data_dir, legacy_file_name + ".html")
        bz2_path = os.path.join(self.data_dir, legacy_file_name + ".bz2")

        if os.path.exists(html_path):
            self.cache[clean_url] = legacy_file_name + ".html"
            return True
        if os.path.exists(bz2_path):
            self.cache[clean_url] = legacy_file_name + ".bz2"
            return True

        return False

    def get_cached_page(self, url: str) -> str:
        file_name = self.cache[self.get_clean_url(url)]

        primary_loc = os.path.join(self.data_dir, file_name)
        secondary_loc = os.path.join(self.secondary_lookup_dir, file_name)
        if os.path.exists(primary_loc):
            return self._read_file(primary_loc)
        if self.secondary_lookup_dir and os.path.exists(secondary_loc):
            return self._read_file(secondary_loc)
        raise FileNotFoundError(file_name)

    def is_cache_entry_usable(self, url: str, max_age_days: Optional[int] = None, min_version: Optional[int] = None) -> bool:
        if not self.page_exists_in_cache(url):
            return False

        metadata = self.metadata.get(self.get_clean_url(url))
        if not metadata:
            return False

        version = metadata.get("version")
        if min_version is not None and (version is None or version < min_version):
            return False

        if max_age_days is not None:
            lookup_date = metadata.get("lookup_date")
            if not lookup_date:
                return False
            try:
                entry_date = datetime.fromisoformat(lookup_date.replace("Z", "+00:00"))
            except ValueError:
                return False
            if datetime.now(entry_date.tzinfo) - entry_date > timedelta(days=max_age_days):
                return False

        return True

    def get_clean_url(self, url: str) -> str:
        return url.split("?")[0]

    def _load_cache(self) -> Dict[str, str]:
        if not os.path.exists(self.webcache_file):
            legacy_path = os.path.join(self.data_dir, WEBCACHE_FILE)
            if not os.path.exists(legacy_path):
                return {}
            with open(legacy_path) as file_handle:
                return json.load(file_handle)

        with open(self.webcache_file) as file_handle:
            return json.load(file_handle)

    def _load_metadata(self) -> Dict[str, dict]:
        if not os.path.exists(self.metadata_file):
            return {}
        with open(self.metadata_file) as file_handle:
            return json.load(file_handle)

    def _read_file(self, file_path: str) -> str:
        if file_path.endswith(".html"):
            with open(file_path) as file_handle:
                return file_handle.read()
        with bz2.open(file_path, "rt") as file_handle:
            return file_handle.read()

    def _utc_now(self) -> str:
        return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
