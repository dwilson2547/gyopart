import json
import os
import shutil
import sys
import time
import urllib.request
from datetime import datetime, timezone

from cache_client import WebCacheClient
from imgcache_client import ImgCacheClient
from request_auth_client import RequestAuthClient
from sqlalchemy import create_engine

from config import Config
from utils.BrowserUtil import BrowserUtil
from utils.CachedParser import CachedParser
from utils.Configs import Configs
from utils.Constants import keys, PageType, SaveFiles
from utils.Exceptions import (
    NoProgressException, PageRetrievalError, Browser429Error,
)
from utils.pg_schema import scrape_run_table
from utils.pg_writer import get_or_create_manufacturer, write_car_data
from utils.TreeBuilder import TreeBuilder


class PartsDirectScraper:

    def __init__(self, config_name: str, instance_name: str):
        cfg = Configs.get(config_name)
        self.BASE_URL = cfg["base_url"]
        self.DATA_DIR = cfg["data_dir"]
        self.config_name = config_name
        self.instance_name = instance_name
        self.progress = False
        self.page_request_delay = Config.PAGE_REQUEST_DELAY

        self.PARTS_FILE = os.path.join(self.DATA_DIR, SaveFiles.PARTS_FILE)
        self.TREE_FILE = os.path.join(self.DATA_DIR, SaveFiles.TREE_FILE)
        self.BLANK_TREE = os.path.join(self.DATA_DIR, SaveFiles.BLANK_TREE_FILE)
        self.BACKUPS_DIR = os.path.join(self.DATA_DIR, SaveFiles.BACKUPS_DIR)

        for d in (self.DATA_DIR, self.BACKUPS_DIR):
            os.makedirs(d, exist_ok=True)

        self.cached_parser = CachedParser(self.BASE_URL)
        self.pi_engine = create_engine(Config.PARTS_DATABASE_URL)

    # ── cache helpers ──────────────────────────────────────────────────────────

    def _fetch_and_cache(
        self,
        url: str,
        browser_util: BrowserUtil,
        web_cache: WebCacheClient,
        request_auth: RequestAuthClient,
        retries: int = 0,
    ) -> str:
        if retries > 2:
            raise PageRetrievalError(f"Page retrieval failed after retries: {url}")

        time.sleep(self.page_request_delay)
        domain = self.BASE_URL.split("//")[-1].split("/")[0]
        with request_auth.acquire(domain) as permit:
            browser_util.navigate(url)
            page_source = browser_util.get_page_source()
            permit.set_status(200)

        try:
            if self.cached_parser.check_page(page_source):
                web_cache.store(url, page_source, client_name=Config.CLIENT_NAME)
                self.progress = True
                return page_source
            else:
                return self._fetch_and_cache(url, browser_util, web_cache, request_auth, retries + 1)
        except Browser429Error:
            self.page_request_delay += 0.5
            time.sleep(45)
            return self._fetch_and_cache(url, browser_util, web_cache, request_auth, retries + 1)

    def _get_page(
        self,
        url: str,
        browser_util: BrowserUtil,
        web_cache: WebCacheClient,
        request_auth: RequestAuthClient,
    ) -> str:
        entry = web_cache.get(url, max_age=Config.CACHE_MAX_AGE_SECONDS)
        if entry:
            page_source = entry["content"]
            if not self.cached_parser.check_cached_page(page_source):
                web_cache.delete(entry["content_hash"])
                return self._fetch_and_cache(url, browser_util, web_cache, request_auth)
            return page_source
        return self._fetch_and_cache(url, browser_util, web_cache, request_auth)

    # ── image helpers ──────────────────────────────────────────────────────────

    def _cache_image(self, url: str, img_cache: ImgCacheClient) -> str | None:
        if url.startswith("//"):
            url = "https:" + url
        fname = url.split("/")[-1]
        if not fname:
            return None
        meta = img_cache.lookup(url, bucket=Config.IMG_BUCKET)
        if meta:
            return meta.get("content_hash")
        try:
            time.sleep(1)
            with urllib.request.urlopen(url, timeout=30) as resp:
                img_bytes = resp.read()
            result = img_cache.store(
                url=url, file_bytes=img_bytes,
                client_name=Config.CLIENT_NAME,
                bucket=Config.IMG_BUCKET,
                filename=fname,
            )
            return result.get("content_hash") if result else None
        except Exception as ex:
            print(f"Failed to cache image {url}: {ex}")
            return None

    # ── state helpers ──────────────────────────────────────────────────────────

    def load(self):
        tree = parts = None
        try:
            with open(self.TREE_FILE) as f:
                tree = json.load(f)
        except Exception:
            pass
        try:
            with open(self.PARTS_FILE) as f:
                parts = json.load(f)
        except Exception:
            pass
        return tree, parts

    def save(self, tree, parts, fresh_run: bool = False):
        print("saving...")
        if tree:
            with open(self.TREE_FILE, "w") as f:
                f.write(json.dumps(tree))
            if fresh_run:
                with open(self.BLANK_TREE, "w") as f:
                    f.write(json.dumps(tree))
        if parts:
            with open(self.PARTS_FILE, "w") as f:
                f.write(json.dumps(parts))
        try:
            if os.path.exists(self.TREE_FILE):
                shutil.copyfile(self.TREE_FILE, os.path.join(self.BACKUPS_DIR, SaveFiles.TREE_FILE))
            if os.path.exists(self.PARTS_FILE):
                shutil.copyfile(self.PARTS_FILE, os.path.join(self.BACKUPS_DIR, SaveFiles.PARTS_FILE))
        except Exception as ex:
            print(f"Backup failed: {ex}")
        print("finished")

    # ── scrape_run audit ───────────────────────────────────────────────────────

    def _open_scrape_run(self) -> int:
        with self.pi_engine.begin() as conn:
            row = conn.execute(
                scrape_run_table.insert()
                .values(manufacturer=self.config_name, started_at=datetime.now(timezone.utc), success=False)
                .returning(scrape_run_table.c.id)
            )
            return row.scalar_one()

    def _close_scrape_run(
        self, run_id: int, cars_processed: int, new_parts: int,
        success: bool, error: str | None = None,
    ):
        with self.pi_engine.begin() as conn:
            conn.execute(
                scrape_run_table.update()
                .where(scrape_run_table.c.id == run_id)
                .values(
                    completed_at=datetime.now(timezone.utc),
                    cars_processed=cars_processed,
                    new_parts=new_parts,
                    success=success,
                    error_message=error,
                )
            )

    # ── main scrape ────────────────────────────────────────────────────────────

    def scrape(self):
        fresh_run = False
        tree, parts = self.load()

        if not tree:
            fresh_run = True
            tree = TreeBuilder(self.BASE_URL).scrape_car_list()
        if not parts:
            parts = {}

        if fresh_run:
            self.save(tree, parts, fresh_run=True)

        run_id = self._open_scrape_run()
        cars_processed = 0
        new_parts = 0

        try:
            with self.pi_engine.begin() as conn:
                manufacturer_id = get_or_create_manufacturer(conn, self.config_name, self.BASE_URL)

            cars_processed_ref = [0]
            new_parts_ref = [0]

            with WebCacheClient(Config.WEBCACHE_URL, timeout=Config.WEBCACHE_TIMEOUT) as web_cache, \
                 ImgCacheClient(Config.IMGCACHE_URL, timeout=Config.IMGCACHE_TIMEOUT) as img_cache, \
                 RequestAuthClient(Config.REQUEST_AUTH_SERVER_URL) as request_auth:

                self.traverse_tree(
                    tree, parts, web_cache, img_cache, request_auth,
                    manufacturer_id, cars_processed_ref, new_parts_ref,
                )
                cars_processed = cars_processed_ref[0]
                new_parts = new_parts_ref[0]

        except Exception as ex:
            self._close_scrape_run(run_id, cars_processed, new_parts, success=False, error=str(ex)[:1000])
            raise

        self._close_scrape_run(run_id, cars_processed, new_parts, success=True)
        self.save(tree, parts)

    def traverse_tree(
        self, tree, parts, web_cache, img_cache, request_auth,
        manufacturer_id, cars_processed_ref, new_parts_ref,
    ):
        try:
            for yr in list(tree.keys()):
                year = tree[yr]
                if year.get("done"):
                    continue
                for mk in list(year[keys.MAKES].keys()):
                    make = year[keys.MAKES][mk]
                    for mdl in list(make[keys.MODELS].keys()):
                        model = make[keys.MODELS][mdl]
                        for trm in list(model[keys.TRIMS].keys()):
                            trim = model[keys.TRIMS][trm]
                            for eng in list(trim[keys.ENGINES].keys()):
                                engine = trim[keys.ENGINES][eng]
                                if engine.get("done"):
                                    continue
                                parts_before = len(parts)
                                img_hashes = self.process_car_data(
                                    engine[keys.PAGE_URL], engine, parts,
                                    web_cache, img_cache, request_auth,
                                )
                                engine["done"] = True
                                cars_processed_ref[0] += 1
                                new_parts_ref[0] += len(parts) - parts_before

                                car_context = {
                                    "year": yr,
                                    "make_url": mk,
                                    "make_name": make.get("ui", mk),
                                    "model_url": mdl,
                                    "model_name": model.get("ui", mdl),
                                    "trim_url": trm,
                                    "trim_name": trim.get("ui", trm),
                                    "engine_url": eng,
                                    "engine_name": engine.get("ui", eng),
                                    "base_url": engine[keys.PAGE_URL],
                                }
                                write_car_data(
                                    self.pi_engine, car_context,
                                    engine.get(keys.DIAGRAMS, []),
                                    parts, manufacturer_id,
                                    imgcache_hashes=img_hashes,
                                )
                                self.save(tree, parts)
                year["done"] = True

        except Exception as ex:
            self.save(tree, parts)
            if not self.progress:
                raise NoProgressException(ex)
            raise
        except KeyboardInterrupt:
            self.save(tree, parts)
            sys.exit()

    def process_car_data(
        self, url, engine, parts, web_cache, img_cache, request_auth,
    ) -> dict:
        if "categories" in engine:
            engine.pop("categories")
        if keys.PARTS not in engine:
            engine[keys.PARTS] = []
        if keys.DIAGRAMS not in engine:
            engine[keys.DIAGRAMS] = []

        img_hashes: dict[str, str] = {}
        browser_util = BrowserUtil(debug_port="")

        if keys.CATEGORY_LINKS not in engine:
            try:
                categories_page = self._get_page(url, browser_util, web_cache, request_auth)
            except PageRetrievalError:
                print(f"Failed to retrieve categories page, skipping. url: {url}")
                engine[keys.CATEGORY_LINKS] = []
                engine["skipped"] = True
                browser_util.close()
                return img_hashes
            engine[keys.CATEGORY_LINKS] = self.cached_parser.parse_cached_page(
                categories_page, PageType.CATEGORIES
            )

        for category_link in engine[keys.CATEGORY_LINKS]:
            if category_link["done"]:
                continue
            category_url = category_link["url"]

            try:
                diagram_page = self._get_page(category_url, browser_util, web_cache, request_auth)
            except PageRetrievalError:
                print(f"Failed to retrieve diagram page, skipping. url: {category_url}")
                category_link["done"] = True
                category_link["skipped"] = True
                continue

            additional_vars = {"base_car_url": url, "category_page_url": category_url}
            diagrams, part_list = self.cached_parser.parse_cached_page(
                diagram_page, PageType.DIAGRAMS, additional_vars
            )

            for diagram in diagrams["diagrams"]:
                img_url = diagram.get("img_url", "")
                if img_url and diagram.get("img"):
                    full_url = "https:" + img_url if img_url.startswith("//") else img_url
                    content_hash = self._cache_image(full_url, img_cache)
                    if content_hash:
                        img_hashes[full_url] = content_hash

            engine[keys.DIAGRAMS].append(diagrams)

            for part_number in part_list:
                if part_number not in engine[keys.PARTS]:
                    engine[keys.PARTS].append(part_number)

            parts_to_fetch = [
                {"part_number": pn, "url": pu}
                for pn, pu in part_list.items()
                if pn not in parts
            ]
            for part in parts_to_fetch:
                pn = part["part_number"]
                try:
                    part_page = self._get_page(part["url"], browser_util, web_cache, request_auth)
                except PageRetrievalError:
                    parts[pn] = {"title": "", "part_number": pn, "url": part["url"],
                                 "images": [], "details": {}, "skipped": True}
                    continue

                part_data = self.cached_parser.parse_cached_page(part_page, PageType.PART)
                part_data["url"] = part["url"]
                parts[pn] = part_data

                for img_rec in part_data.get("images", []):
                    for slot in ("main", "preview", "thumb"):
                        slot_data = img_rec.get(slot)
                        if not slot_data:
                            continue
                        raw_url = slot_data.get("url", "")
                        full_url = "https:" + raw_url if raw_url.startswith("//") else raw_url
                        content_hash = self._cache_image(full_url, img_cache)
                        if content_hash:
                            img_hashes[full_url] = content_hash

            category_link["done"] = True

        browser_util.close()
        return img_hashes
