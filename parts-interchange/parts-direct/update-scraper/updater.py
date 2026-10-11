from __future__ import annotations

import json
import os
import shutil
from datetime import datetime as dt
from typing import TYPE_CHECKING, Dict
from urllib.parse import urlparse

import requests
from bootstrap import ensure_singlethreaded_src_path
from recent_tree_builder import RecentTreeBuilder
from tree_merge import merge_recent_tree

ensure_singlethreaded_src_path()

from cache_client import ImgCacheClient, WebCacheClient
from playwright_stealth import Stealth
from request_auth_client import RequestAuthClient
from utils.CachedParser import CachedParser
from utils.Constants import PageType, SaveFiles, keys
from utils.Exceptions import Browser403Error, Browser429Error, NoProgressException, PageRetrievalError

if TYPE_CHECKING:
    from playwright.sync_api import Browser, BrowserContext, Page

# Mimic a real Chrome to pass Cloudflare bot detection.
# The sec-ch-ua header must be overridden at the HTTP level because Chromium
# embeds "HeadlessChrome" there even when the user-agent is overridden via JS.
_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
)
_SEC_CH_UA = '"Google Chrome";v="121", "Not A(Brand";v="99", "Chromium";v="121"'


class RecentPartsDirectUpdater:
    def __init__(
        self,
        config_name: str,
        years_to_refresh: int = 7,
        max_cache_age_days: int = 30,
        current_year: int = None,
    ):
        from utils.Configs import Configs
        cfg = Configs.get(config_name)

        self.BASE_URL = cfg["base_url"]
        self.DATA_DIR = cfg["data_dir"]
        self.config_name = config_name
        self.progress = False
        self.save_time = dt.now().timestamp()
        self.years_to_refresh = years_to_refresh
        self.max_cache_age_days = max_cache_age_days
        self.current_year = current_year or dt.utcnow().year

        self.PARTS_FILE = os.path.join(self.DATA_DIR, SaveFiles.PARTS_FILE)
        self.IMAGES_FILE = os.path.join(self.DATA_DIR, SaveFiles.IMAGES_FILE)
        self.TREE_FILE = os.path.join(self.DATA_DIR, SaveFiles.TREE_FILE)
        self.BLANK_TREE = os.path.join(self.DATA_DIR, SaveFiles.BLANK_TREE_FILE)
        self.BACKUPS_DIR = os.path.join(self.DATA_DIR, SaveFiles.BACKUPS_DIR)

        os.makedirs(self.DATA_DIR, exist_ok=True)
        os.makedirs(self.BACKUPS_DIR, exist_ok=True)

        webcache_url = os.environ["WEBCACHE_URL"]
        imgcache_url = os.environ["IMGCACHE_URL"]
        request_auth_url = os.environ["REQUEST_AUTH_URL"]

        self.web_cache = WebCacheClient(webcache_url)
        self.img_cache = ImgCacheClient(imgcache_url)
        self.request_auth = RequestAuthClient(request_auth_url)
        self.cached_parser = CachedParser(self.BASE_URL)
        self._browser: "Browser | None" = None
        self._stealth = Stealth(
            navigator_user_agent_override=_CHROME_UA,
            sec_ch_ua_override=_SEC_CH_UA,
        )

    def _new_context(self) -> "BrowserContext":
        """Create a browser context with Cloudflare-bypass stealth settings applied."""
        context = self._browser.new_context(
            user_agent=_CHROME_UA,
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            extra_http_headers={
                "sec-ch-ua": _SEC_CH_UA,
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
            },
        )
        self._stealth.apply_stealth_sync(context)
        return context

    # ------------------------------------------------------------------ #
    # Persistence                                                          #
    # ------------------------------------------------------------------ #

    def load(self):
        tree = parts = images = None
        try:
            with open(self.TREE_FILE) as f:
                tree = json.load(f)
        except Exception:
            print("No existing tree, starting fresh")
        try:
            with open(self.PARTS_FILE) as f:
                parts = json.load(f)
        except Exception:
            pass
        try:
            with open(self.IMAGES_FILE) as f:
                images = json.load(f)
        except Exception:
            pass
        return tree, parts, images

    def save(self, tree, parts, images, fresh_run=False, low_priority_save=False):
        curr_time = dt.now().timestamp()
        if curr_time - self.save_time < 1800 and low_priority_save:
            print("low priority save, skipping")
            return
        try:
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
            if images:
                with open(self.IMAGES_FILE, "w") as f:
                    f.write(json.dumps(images))
            self._create_backups()
            self.save_time = curr_time
            print("save complete")
        except KeyboardInterrupt:
            print("Saving now, try again once finished.")
            self.save(tree, parts, images)
        except Exception as ex:
            print(f"Save failed: {ex}")

    def _create_backups(self):
        try:
            for src, name in [
                (self.TREE_FILE, SaveFiles.TREE_FILE),
                (self.IMAGES_FILE, SaveFiles.IMAGES_FILE),
                (self.PARTS_FILE, SaveFiles.PARTS_FILE),
            ]:
                if os.path.exists(src):
                    shutil.copyfile(src, os.path.join(self.BACKUPS_DIR, name))
        except Exception as ex:
            print(f"Backup failed: {ex}")

    # ------------------------------------------------------------------ #
    # Page fetching — Playwright + WebCacheClient                          #
    # ------------------------------------------------------------------ #

    def get_rendered_page(self, url: str, page: "Page") -> str:
        """Return rendered HTML for url. Serves from webcache when fresh; otherwise
        navigates with Playwright, validates the content, and stores it in webcache."""
        max_age = self.max_cache_age_days * 86400
        cached = self.web_cache.get(url, max_age=max_age)
        if cached:
            content = cached["content"]
            if self.cached_parser.check_cached_page(content):
                self.progress = True
                return content
            # Cached page is a stale error page — evict and re-render
            self.web_cache.delete(cached["content_hash"])

        domain = urlparse(url).netloc
        with self.request_auth.acquire(domain) as permit:
            response = page.goto(url, wait_until="networkidle", timeout=60_000)
            permit.set_status(response.status if response else 0)

        if response and response.status == 404:
            raise PageRetrievalError(f"404: {url}")

        content = page.content()

        try:
            ok = self.cached_parser.check_page(content)
        except (Browser429Error, Browser403Error):
            raise  # caller decides what to do; don't cache error pages
        except Exception:
            ok = False

        if not ok:
            raise PageRetrievalError(f"Page not found: {url}")

        self.web_cache.store(url, content, client_name=f"parts-direct-{self.config_name}")
        self.progress = True
        return content

    # ------------------------------------------------------------------ #
    # Image handling                                                       #
    # ------------------------------------------------------------------ #

    def save_image(self, url: str, file_name: str) -> bool:
        try:
            if self.img_cache.lookup(url):
                return True
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            self.img_cache.store(
                url=url,
                file_bytes=resp.content,
                client_name=f"parts-direct-{self.config_name}",
                filename=file_name,
            )
            return True
        except Exception as ex:
            print(f"Failed to save image at {url}: {ex}")
            return False

    # ------------------------------------------------------------------ #
    # Scrape orchestration                                                 #
    # ------------------------------------------------------------------ #

    def scrape(self):
        tree, parts, images = self.load()
        existing_tree = tree or {}
        parts = parts or {}
        images = images or {}

        from playwright.sync_api import sync_playwright
        browserless_url = os.environ.get("BROWSERLESS_URL")
        with sync_playwright() as p:
            if browserless_url:
                self._browser = p.chromium.connect_over_cdp(browserless_url)
            else:
                self._browser = p.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"],
                )
            try:
                recent_tree = self._build_recent_tree()
                merged_tree = merge_recent_tree(existing_tree, recent_tree)
                self.save(merged_tree, parts, images, fresh_run=not bool(existing_tree))
                self.traverse_recent_tree(merged_tree, recent_tree, parts, images)
            finally:
                self._browser.close()
                self._browser = None

    def _build_recent_tree(self) -> Dict:
        """Navigate to site homepage (passes Cloudflare challenge) then build the vehicle tree.
        Uses a dedicated browser context so AJAX calls share the Cloudflare cookie jar."""
        context = self._new_context()
        try:
            page = context.new_page()
            domain = urlparse(self.BASE_URL).netloc
            with self.request_auth.acquire(domain) as permit:
                resp = page.goto(self.BASE_URL, wait_until="networkidle", timeout=60_000)
                permit.set_status(resp.status if resp else 0)
            csrf_token = page.evaluate(
                "() => document.querySelector('meta[name=\"csrf-token\"]')?.content || null"
            )
            print(f"Homepage loaded, building vehicle tree...")
            return RecentTreeBuilder(
                self.BASE_URL,
                years_to_refresh=self.years_to_refresh,
                request_auth=self.request_auth,
                current_year=self.current_year,
                csrf_token=csrf_token,
            ).scrape_car_list(page=page)
        finally:
            context.close()

    def traverse_recent_tree(self, merged_tree: Dict, recent_tree: Dict, parts: Dict, images: Dict):
        year_key = make_key = model_key = trim_key = engine_key = None
        try:
            for year_key in sorted(recent_tree.keys()):
                merged_year = merged_tree[year_key]
                recent_year = recent_tree[year_key]
                for make_key in sorted(recent_year[keys.MAKES].keys()):
                    merged_make = merged_year[keys.MAKES][make_key]
                    recent_make = recent_year[keys.MAKES][make_key]
                    for model_key in sorted(recent_make[keys.MODELS].keys()):
                        merged_model = merged_make[keys.MODELS][model_key]
                        recent_model = recent_make[keys.MODELS][model_key]
                        for trim_key in sorted(recent_model[keys.TRIMS].keys()):
                            merged_trim = merged_model[keys.TRIMS][trim_key]
                            recent_trim = recent_model[keys.TRIMS][trim_key]
                            for engine_key in sorted(recent_trim[keys.ENGINES].keys()):
                                engine = merged_trim[keys.ENGINES][engine_key]
                                engine["done"] = False
                                print(f"Processing: {year_key} {make_key} {model_key} {trim_key} {engine_key}")
                                self.process_car_data(engine[keys.PAGE_URL], engine, parts, images)
                                engine["done"] = True
                                self.save(merged_tree, parts, images, low_priority_save=True)
                merged_year["done"] = True
            self.save(merged_tree, parts, images)
        except Exception as ex:
            self.save(merged_tree, parts, images)
            if not self.progress:
                raise NoProgressException(ex)
            raise ex

    def process_car_data(self, url: str, engine: Dict, parts: Dict, images: Dict):
        """Scrape all categories, diagrams, and parts for one car config.
        Opens a fresh browser context so cookies are isolated per car."""
        engine.pop("categories", None)
        engine[keys.PARTS] = []
        engine[keys.DIAGRAMS] = []

        context = self._new_context()
        try:
            page = context.new_page()

            try:
                categories_page_source = self.get_rendered_page(url, page)
            except PageRetrievalError:
                print(f"Failed to retrieve categories page, skipping. url: {url}")
                engine[keys.CATEGORY_LINKS] = []
                engine["skipped"] = True
                return

            engine[keys.CATEGORY_LINKS] = self.cached_parser.parse_cached_page(
                categories_page_source, PageType.CATEGORIES
            )

            for category_page_link in engine[keys.CATEGORY_LINKS]:
                category_page_url = category_page_link["url"]

                try:
                    diagram_page_source = self.get_rendered_page(category_page_url, page)
                except PageRetrievalError:
                    print(f"Failed to retrieve diagram page, skipping. url: {category_page_url}")
                    category_page_link["done"] = True
                    category_page_link["skipped"] = True
                    continue

                additional_vars = {"base_car_url": url, "category_page_url": category_page_url}
                diagrams, part_list = self.cached_parser.parse_cached_page(
                    diagram_page_source, PageType.DIAGRAMS, additional_vars
                )

                for diagram in diagrams["diagrams"]:
                    img_name = diagram["img"]
                    if img_name and img_name not in images:
                        img_url = diagram["img_url"]
                        if not img_url.startswith("https"):
                            img_url = "https:" + img_url
                        saved = self.save_image(img_url, img_name)
                        images[img_name] = {"url": img_url, "alt": diagram["alt_text"], "saved": saved}

                engine[keys.DIAGRAMS].append(diagrams)

                for part_number, part_page_url in part_list.items():
                    if part_number not in engine[keys.PARTS]:
                        engine[keys.PARTS].append(part_number)

                    if not self._should_refresh_part(parts, part_number, part_page_url):
                        parts[part_number]["url"] = part_page_url
                        continue

                    try:
                        part_page_source = self.get_rendered_page(part_page_url, page)
                    except PageRetrievalError:
                        print(f"Page retrieval failed, skipping part: {part_number}")
                        parts[part_number] = {
                            "title": "", "part_number": part_number, "url": part_page_url,
                            "images": [], "details": {}, "fitment": [], "skipped": True,
                        }
                        continue

                    print(f"Scraping part: {part_number}")
                    part_data = self.cached_parser.parse_cached_page(part_page_source, PageType.PART)
                    part_data["url"] = part_page_url
                    parts[part_number] = part_data

                    for part_image_rec in part_data.get("images", []):
                        for img_cat in ["main", "preview", "thumb"]:
                            img_entry = part_image_rec.get(img_cat)
                            if not img_entry:
                                continue
                            part_img_url = img_entry["url"]
                            if not part_img_url.startswith("https"):
                                part_img_url = "https:" + part_img_url
                            part_img_name = part_img_url.split("/")[-1]
                            if part_img_name not in images:
                                saved = self.save_image(part_img_url, part_img_name)
                                images[part_img_name] = {"url": part_img_url, "alt": None, "saved": saved}

                category_page_link["done"] = True
        finally:
            context.close()

    def _should_refresh_part(self, parts: Dict, part_number: str, part_page_url: str) -> bool:
        if part_number not in parts:
            return True
        existing = parts[part_number]
        if existing.get("url") != part_page_url:
            return True
        return existing.get("skipped", False)
