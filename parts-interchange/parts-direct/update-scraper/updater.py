import json
import os
import shutil
import sys
import time
import urllib.request
from datetime import datetime as dt
from typing import Dict

from bootstrap import ensure_singlethreaded_src_path
from recent_tree_builder import RecentTreeBuilder
from tree_merge import merge_recent_tree
from versioned_browser_cache import VersionedBrowserCache

ensure_singlethreaded_src_path()

from utils.Configs import Configs
from utils.Constants import BUCKET_NAME, INFLUX_MEASURE, PageType, SaveFiles, keys
from utils.Exceptions import Browser429Error, NoProgressException, PageRetrievalError


class RecentPartsDirectUpdater:
    def __init__(
        self,
        config_name: str,
        instance_name: str,
        years_to_refresh: int = 7,
        max_cache_age_days: int = 30,
        cache_version: int = 1,
        current_year: int = None,
    ):
        cfg = Configs.get(config_name)

        self.BASE_URL = cfg["base_url"]
        self.DATA_DIR = cfg["data_dir"]
        self.DEBUG_PORT = cfg["port"]
        self.config_name = config_name
        self.progress = False
        self.page_request_delay = 3.5
        self.save_time = dt.now().timestamp()
        self.years_to_refresh = years_to_refresh
        self.max_cache_age_days = max_cache_age_days
        self.cache_version = cache_version
        self.current_year = current_year or dt.utcnow().year
        self.minimum_year = self.current_year - self.years_to_refresh + 1

        self.PARTS_FILE = os.path.join(self.DATA_DIR, SaveFiles.PARTS_FILE)
        self.IMG_DIR = os.path.join(self.DATA_DIR, SaveFiles.IMAGES_DIR)
        self.IMAGES_FILE = os.path.join(self.DATA_DIR, SaveFiles.IMAGES_FILE)
        self.TREE_FILE = os.path.join(self.DATA_DIR, SaveFiles.TREE_FILE)
        self.BLANK_TREE = os.path.join(self.DATA_DIR, SaveFiles.BLANK_TREE_FILE)

        self.BACKUPS_DIR = os.path.join(self.DATA_DIR, SaveFiles.BACKUPS_DIR)
        self.BACKUP_TREE_FILE = os.path.join(self.BACKUPS_DIR, SaveFiles.TREE_FILE)
        self.BACKUP_IMAGES_FILE = os.path.join(self.BACKUPS_DIR, SaveFiles.IMAGES_FILE)
        self.BACKUP_PARTS_FILE = os.path.join(self.BACKUPS_DIR, SaveFiles.PARTS_FILE)

        if not os.path.exists(self.DATA_DIR):
            os.mkdir(self.DATA_DIR)
        if not os.path.exists(self.IMG_DIR):
            os.mkdir(self.IMG_DIR)
        if not os.path.exists(self.BACKUPS_DIR):
            os.mkdir(self.BACKUPS_DIR)

        from utils.BucketUtils import BucketUtils
        from utils.CachedParser import CachedParser
        from utils.InfluxUtils import InfluxUtils

        self.influx_utils = InfluxUtils(instance=instance_name)
        self.bucket_utils = BucketUtils()
        self.browser_cache = VersionedBrowserCache(config_name, self.DATA_DIR, cache_version=self.cache_version)
        self.cached_parser = CachedParser(self.BASE_URL)

    def load(self):
        tree = None
        parts = None
        images = None
        try:
            with open(self.TREE_FILE) as tree_file:
                tree = json.load(tree_file)
        except Exception:
            print("Loading failed, assuming new run")
        try:
            with open(self.PARTS_FILE) as parts_file:
                parts = json.load(parts_file)
        except Exception:
            pass
        try:
            with open(self.IMAGES_FILE) as images_file:
                images = json.load(images_file)
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
                with open(self.TREE_FILE, "w") as tree_file:
                    tree_file.write(json.dumps(tree))
                if fresh_run:
                    with open(self.BLANK_TREE, "w") as blank_tree_file:
                        blank_tree_file.write(json.dumps(tree))
            if parts:
                with open(self.PARTS_FILE, "w") as parts_file:
                    parts_file.write(json.dumps(parts))
            if images:
                with open(self.IMAGES_FILE, "w") as images_file:
                    images_file.write(json.dumps(images))
            self.browser_cache.save()
            self.create_backups()
            self.save_time = curr_time
            print("finished")
        except KeyboardInterrupt:
            print("Saving now, try again once finished.")
            self.save(tree, parts, images)
        except Exception as ex:
            print(ex)
            print("Failed to save in default directory, saving to bucket and then killing process")
            try:
                self.bucket_utils.dump_json_to_bucket(BUCKET_NAME, self.config_name, SaveFiles.TREE_FILE, tree)
                self.bucket_utils.dump_json_to_bucket(BUCKET_NAME, self.config_name, SaveFiles.PARTS_FILE, parts)
                self.bucket_utils.dump_json_to_bucket(BUCKET_NAME, self.config_name, SaveFiles.IMAGES_FILE, images)
                self.browser_cache.bucket_save(self.bucket_utils)
            except Exception:
                print("Failed to save to bucket, ending process")
                sys.exit(0)

            print("Bucket save complete, ending process")
            sys.exit(0)

    def create_backups(self):
        try:
            shutil.copyfile(self.TREE_FILE, self.BACKUP_TREE_FILE)
            if os.path.exists(self.IMAGES_FILE):
                shutil.copyfile(self.IMAGES_FILE, self.BACKUP_IMAGES_FILE)
            if os.path.exists(self.PARTS_FILE):
                shutil.copyfile(self.PARTS_FILE, self.BACKUP_PARTS_FILE)
        except Exception:
            print("Creating backups failed, exiting now")
            sys.exit(0)

    def save_image(self, url, file_name):
        file_path = os.path.join(self.IMG_DIR, file_name)

        print("Saving image: " + file_name)

        if os.path.exists(file_path):
            print("Image already downloaded")
        else:
            time.sleep(2)
            try:
                urllib.request.urlretrieve(url, file_path)
            except Exception:
                print("Failed to save image at url: " + url)
                return False, False

        try:
            self.bucket_utils.upload_image_to_bucket(BUCKET_NAME, self.config_name, file_name, file_path)
        except Exception as ex:
            print("Failed to upload image to bucket")
            print(ex)
            return True, False

        return True, True

    def add_page_to_cache(self, url, browser_util, retries=0):
        if retries > 2:
            raise PageRetrievalError("404 caught when retrieving page at url: " + url)

        time.sleep(self.page_request_delay)

        browser_util.navigate(url)
        page_source = browser_util.get_page_source()

        try:
            if self.cached_parser.check_page(page_source):
                self.browser_cache.add_to_cache(url, page_source)
                self.progress = True
                return page_source
            print("page retrieval failed, retrying...")
            return self.add_page_to_cache(url, browser_util, retries + 1)
        except Browser429Error:
            print("429 caught, slowing down a little")
            self.page_request_delay += 0.5
            time.sleep(45)
            return self.add_page_to_cache(url, browser_util, retries + 1)

    def scrape(self):
        tree, parts, images = self.load()
        existing_tree = tree or {}
        parts = parts or {}
        images = images or {}

        recent_tree = RecentTreeBuilder(
            self.BASE_URL,
            years_to_refresh=self.years_to_refresh,
            current_year=self.current_year,
        ).scrape_car_list()
        merged_tree = merge_recent_tree(existing_tree, recent_tree)

        self.save(merged_tree, parts, images, fresh_run=not bool(existing_tree))
        self.traverse_recent_tree(merged_tree, recent_tree, parts, images)

    def get_and_cache_page_source(self, url: str, browser_util) -> str:
        use_cache = self.browser_cache.is_cache_entry_usable(
            url,
            max_age_days=self.max_cache_age_days,
            min_version=self.cache_version,
        )

        if use_cache:
            page_source = self.browser_cache.get_cached_page(url)
            if not self.cached_parser.check_cached_page(page_source):
                self.browser_cache.remove_from_cache(url)
                return self.get_and_cache_page_source(url, browser_util)
            self.progress = True
            return page_source, True

        page_source = self.add_page_to_cache(url, browser_util)
        return page_source, False

    def get_image_name(self, url: str):
        return url.split("/")[-1]

    def traverse_recent_tree(self, merged_tree: Dict, recent_tree: Dict, parts: Dict, images: Dict):
        year_key = None
        make_key = None
        model_key = None
        trim_key = None
        engine_key = None
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
                                print(self.influx_utils.get_influx_stats(year_key, make_key, model_key, trim_key, engine_key))
                                self.influx_utils.post_point(
                                    INFLUX_MEASURE,
                                    self.influx_utils.get_tags(),
                                    self.influx_utils.get_influx_stats(year_key, make_key, model_key, trim_key, engine_key),
                                )
                                self.process_car_data(engine[keys.PAGE_URL], engine, parts, images)
                                engine["done"] = True
                                self.save(merged_tree, parts, images, low_priority_save=True)
                merged_year["done"] = True
            self.save(merged_tree, parts, images)
        except Exception as ex:
            self.save(merged_tree, parts, images)
            if not self.progress:
                self.influx_utils.post_point(
                    INFLUX_MEASURE,
                    self.influx_utils.get_tags(),
                    self.influx_utils.get_influx_stats(year_key, make_key, model_key, trim_key, engine_key, False),
                )
                raise NoProgressException(ex)
            raise ex

    def process_car_data(self, url, engine, parts, images):
        engine.pop("categories", None)
        engine[keys.PARTS] = []
        engine[keys.DIAGRAMS] = []

        from utils.BrowserUtil import BrowserUtil

        browser_util = BrowserUtil(self.DEBUG_PORT, proxy="http://192.168.0.240:8118")

        try:
            try:
                categories_page_source, categories_cached = self.get_and_cache_page_source(url, browser_util)
            except PageRetrievalError:
                print("Failed to retrieve categories page, skipping. url: " + url)
                engine[keys.CATEGORY_LINKS] = []
                engine["skipped"] = True
                return

            print("Parsing categories. Cached: " + str(categories_cached))
            engine[keys.CATEGORY_LINKS] = self.cached_parser.parse_cached_page(categories_page_source, PageType.CATEGORIES)

            for category_page_link in engine[keys.CATEGORY_LINKS]:
                category_page_url = category_page_link["url"]

                try:
                    diagram_page_source, diagrams_cached = self.get_and_cache_page_source(category_page_url, browser_util)
                except PageRetrievalError:
                    print("Failed to retrieve diagram page, skipping. url: " + category_page_url)
                    category_page_link["done"] = True
                    category_page_link["skipped"] = True
                    continue

                additional_vars = {
                    "base_car_url": url,
                    "category_page_url": category_page_url,
                }

                diagrams, part_list = self.cached_parser.parse_cached_page(
                    diagram_page_source,
                    PageType.DIAGRAMS,
                    additional_vars,
                    diagrams_cached,
                )

                for diagram in diagrams["diagrams"]:
                    img_name = diagram["img"]
                    if img_name and img_name not in images:
                        image_url = "https:" + diagram["img_url"] if "https" not in diagram["img_url"] else diagram["img_url"]
                        saved, uploaded = self.save_image(image_url, img_name)
                        images[img_name] = {
                            "url": image_url,
                            "alt": diagram["alt_text"],
                            "saved": saved,
                            "uploaded": uploaded,
                        }

                engine[keys.DIAGRAMS].append(diagrams)

                for part_number, part_page_url in part_list.items():
                    if part_number not in engine[keys.PARTS]:
                        engine[keys.PARTS].append(part_number)

                    if not self._should_refresh_part(parts, part_number, part_page_url):
                        parts[part_number]["url"] = part_page_url
                        continue

                    try:
                        part_page_source, part_cached = self.get_and_cache_page_source(part_page_url, browser_util)
                    except PageRetrievalError:
                        print("Page Retrieval error caught, skip this part")
                        parts[part_number] = {
                            "title": "",
                            "part_number": part_number,
                            "url": part_page_url,
                            "images": [],
                            "details": {},
                            "fitment": [],
                            "skipped": True,
                        }
                        continue

                    print("Scraping part number: " + part_number + " Cached: " + str(part_cached))

                    part_data = self.cached_parser.parse_cached_page(part_page_source, PageType.PART)
                    part_data["url"] = part_page_url
                    parts[part_number] = part_data

                    for part_image_rec in part_data["images"]:
                        for img_cat in ["main", "preview", "thumb"]:
                            if not part_image_rec[img_cat]:
                                continue

                            part_img_url = (
                                "https:" + part_image_rec[img_cat]["url"]
                                if "https" not in part_image_rec[img_cat]["url"]
                                else part_image_rec[img_cat]["url"]
                            )
                            part_img_name = self.get_image_name(part_img_url)

                            if part_img_name not in images:
                                saved, uploaded = self.save_image(part_img_url, part_img_name)
                                images[part_img_name] = {
                                    "url": part_img_url,
                                    "alt": None,
                                    "saved": saved,
                                    "uploaded": uploaded,
                                }

                category_page_link["done"] = True
        finally:
            browser_util.close()

    def _should_refresh_part(self, parts: Dict, part_number: str, part_page_url: str) -> bool:
        if part_number not in parts:
            return True

        existing_part = parts[part_number]
        if existing_part.get("url") != part_page_url:
            return True

        return not self.browser_cache.is_cache_entry_usable(
            part_page_url,
            max_age_days=self.max_cache_age_days,
            min_version=self.cache_version,
        )
