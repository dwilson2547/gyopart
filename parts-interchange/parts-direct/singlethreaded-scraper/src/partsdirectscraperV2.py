import json
import os
import shutil
import sys
import time
import urllib.request
from datetime import datetime as dt

from utils.BrowserCache import BrowserCache
from utils.BucketUtils import BucketUtils
from utils.Configs import Configs
from utils.Constants import BUCKET_NAME, INFLUX_MEASURE, keys, PageType, SaveFiles
from utils.Exceptions import NoProgressException, PageRetrievalError, Browser429Error
from utils.InfluxUtils import InfluxUtils
from utils.TreeBuilder import TreeBuilder
from utils.BrowserUtil import BrowserUtil
from utils.CachedParser import CachedParser

"""
Parts Direct Scraper
"""

class PartsDirectScraper():

    def __init__(self, config_name, instance_name):

        cfg = Configs.get(config_name)

        self.BASE_URL = cfg['base_url']
        self.DATA_DIR = cfg['data_dir']
        self.DEBUG_PORT = cfg['port']
        self.config_name = config_name
        self.progress = False
        self.page_request_delay = 3.5
        self.save_time = dt.now().timestamp()

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

        self.influx_utils = InfluxUtils(instance=instance_name)
        self.bucket_utils = BucketUtils()
        self.browser_cache = BrowserCache(config_name, self.DATA_DIR)
        self.cached_parser = CachedParser(self.BASE_URL)

    def load(self):
        tree = None
        parts = None
        images = None
        try:
            with open(self.TREE_FILE) as tf:
                tree = json.load(tf)
        except:
            print('Loading failed, assuming new run')
        try:
            with open(self.PARTS_FILE) as pf:
                parts = json.load(pf)
        except:
            pass
        try:
            with open(self.IMAGES_FILE) as imgf:
                images = json.load(imgf)
        except:
            pass
        return tree, parts, images

    def save(self, tree, parts, images, fresh_run = False, low_priority_save = False):
        
        curr_time = dt.now().timestamp()
        if curr_time - self.save_time < 1800 and low_priority_save:
            print('low priority save, skipping')
            return

        try:
            print('saving...')
            if tree:
                with open(self.TREE_FILE, 'w') as tf:
                    tf.write(json.dumps(tree))
                if fresh_run:
                    with open(self.BLANK_TREE, 'w') as btf:
                        btf.write(json.dumps(tree))
            if parts:
                with open(self.PARTS_FILE, 'w') as pf:
                    pf.write(json.dumps(parts))
            if images:
                with open(self.IMAGES_FILE, 'w') as imgf:
                    imgf.write(json.dumps(images))
            self.browser_cache.save()
            self.create_backups()
            self.save_time = curr_time
            print('finished')
        except KeyboardInterrupt:
            print('Saving now, try again once finished.')
            self.save(tree, parts, images)
        except Exception as ex:
            print(ex)
            print('Failed to save in default directory, saving to bucket and then killing process')
            try:
                self.bucket_utils.dump_json_to_bucket(BUCKET_NAME, self.config_name, SaveFiles.TREE_FILE, tree)
                self.bucket_utils.dump_json_to_bucket(BUCKET_NAME, self.config_name, SaveFiles.PARTS_FILE, parts)
                self.bucket_utils.dump_json_to_bucket(BUCKET_NAME, self.config_name, SaveFiles.IMAGES_FILE, images)
                self.browser_cache.bucket_save(self.bucket_utils)
            except:
                print('Failed to save to bucket, ending process')
                sys.exit(0)
            
            print('Bucket save complete, ending process')
            
            sys.exit(0)

    def create_backups(self):
        try:
            shutil.copyfile(self.TREE_FILE, self.BACKUP_TREE_FILE)
            if os.path.exists(self.IMAGES_FILE):
                shutil.copyfile(self.IMAGES_FILE, self.BACKUP_IMAGES_FILE)
            if os.path.exists(self.PARTS_FILE):
                shutil.copyfile(self.PARTS_FILE, self.BACKUP_PARTS_FILE)
        except:
            print('Creating backups failed, exiting now')
            sys.exit(0)

    def save_image(self, url, file_name):
        file_path = os.path.join(self.IMG_DIR, file_name)
        
        print(f'Saving image: {file_name}')
        
        # Check to see if the image is already downloaded, had some data loss at some point and this helps to rebuild
        if os.path.exists(file_path):
            print('Image already downloaded')
        else:
            time.sleep(2)
            try:
                urllib.request.urlretrieve(url, file_path)
            except:
                print('Failed to save image at url: ' + url)
                return False, False
        
        try:
            self.bucket_utils.upload_image_to_bucket(BUCKET_NAME, self.config_name, file_name, file_path)
        except Exception as ex:
            print('Failed to upload image to bucket')
            print(ex)
            return True, False
        
        return True, True

    def add_page_to_cache(self, url, browser_util, retries=0):
        if retries > 2:
            raise PageRetrievalError(f'404 caught when retrieving page at url: {url}')
        
        time.sleep(self.page_request_delay)
        
        browser_util.navigate(url)
        page_source = browser_util.get_page_source()

        try:
            if self.cached_parser.check_page(page_source):
                self.browser_cache.add_to_cache(url, page_source)
                # Mark progress = true here so once we have a successful page retrieval we know it's working
                self.progress = True
                return page_source
            else:
                print('page retrieval failed, retrying...')
                return self.add_page_to_cache(url, browser_util, retries + 1)
        except Browser429Error:
            print('429 caught, slowing down a little')
            self.page_request_delay += .5
            time.sleep(45)
            return self.add_page_to_cache(url, browser_util, retries + 1)
        
    def get_and_cache_page_source(self, url: str, browser_util) -> str:
        cached = False
        if not self.browser_cache.page_exists_in_cache(url):
            page_source = self.add_page_to_cache(url, browser_util)
        else:
            page_source = self.browser_cache.get_cached_page(url)
            # Check to see if our saved page is valid or not, if not clear the entry and try to re-pull it
            if not self.cached_parser.check_cached_page(page_source):
                print('Cached page invalid, removing and retrying')
                self.browser_cache.remove_from_cache(url)
                return self.get_and_cache_page_source(url, browser_util)
            cached = True
        
        return page_source, cached

    def get_image_name(self, url: str):
        return url.split('/')[-1]

    def scrape(self):
        fresh_run = False
        tree, parts, images = self.load()

        if not tree:
            fresh_run = True
            tree_builder = TreeBuilder(self.BASE_URL)
            tree = tree_builder.scrape_car_list()
        
        if not parts:
            parts = {}

        if not images:
            images = {}

        if fresh_run:
            self.save(tree, parts, images, fresh_run=True)
        
        self.traverse_tree(tree, parts, images)

    def traverse_tree(self, tree, parts, images):
        # Drill down to where the car page urls are saved
        try:
            for yr in list(tree.keys()):
                year = tree[yr]
                for mk in list(year[keys.MAKES].keys()):
                    make = year[keys.MAKES][mk]
                    for mdl in list(make[keys.MODELS].keys()):
                        model = make[keys.MODELS][mdl]
                        for trm in list(model[keys.TRIMS].keys()):
                            trim = model[keys.TRIMS][trm]
                            for eng in list(trim[keys.ENGINES].keys()):
                                # Here we are, now get the parts
                                engine = trim[keys.ENGINES][eng]
                                if 'done' in engine and engine['done']:
                                    continue
                                elif 'part_skip' in engine and engine['part_skip']:
                                    engine['done'] = True
                                    continue
                                else:
                                    engine['done'] = False
                                print(self.influx_utils.get_influx_stats(yr, mk, mdl, trm, eng))
                                self.influx_utils.post_point(INFLUX_MEASURE, self.influx_utils.get_tags(), self.influx_utils.get_influx_stats(yr, mk, mdl, trm, eng))
                                url = engine[keys.PAGE_URL]
                                self.process_car_data(url, engine, parts, images)
                                engine['done'] = True
                                self.save(tree, parts, images, low_priority_save=True)
                year['done'] = True
            self.save(tree, parts, images)

        except Exception as ex:
            self.save(tree, parts, images)
            if not self.progress:
                self.influx_utils.post_point(INFLUX_MEASURE, self.influx_utils.get_tags(), self.influx_utils.get_influx_stats(yr, mk, mdl, trm, eng, False))
                raise NoProgressException(ex)
            raise ex
        except KeyboardInterrupt:
            self.save(tree, parts, images)
            sys.exit()
        
    def process_car_data(self, url, engine, parts, images):

        # Init part and diagram arrays, clean up legacy property categories
        if 'categories' in engine:
            engine.pop('categories')
        if keys.PARTS not in engine:
            engine[keys.PARTS] = []
        if keys.DIAGRAMS not in engine:
            engine[keys.DIAGRAMS] = []

        # Init browser
        browser_util = BrowserUtil(self.DEBUG_PORT, proxy='http://192.168.0.240:8118')

        # Retreive list of category links and add it to the engine record
        if keys.CATEGORY_LINKS not in engine:
            try:
                categories_page_source, cats_cached = self.get_and_cache_page_source(url, browser_util)
            except PageRetrievalError as ex:
                print(f'Failed to retrieve categories page, skipping. url: {url}')
                engine[keys.CATEGORY_LINKS] = []
                engine['skipped'] = True
                return

            print('Parsing categories. Cached: ' + str(cats_cached))
            engine[keys.CATEGORY_LINKS] = self.cached_parser.parse_cached_page(categories_page_source, PageType.CATEGORIES)

        # Loop through category links and build diagrams. Start list of parts that need to be scraped so we can get those next
        for category_page_link in engine[keys.CATEGORY_LINKS]:

            parts_to_scrape = []

            if category_page_link['done']:
                continue

            category_page_url = category_page_link['url']

            try:
                diagram_page_source, diagrams_cached = self.get_and_cache_page_source(category_page_url, browser_util)
            except PageRetrievalError as ex:
                print(f'Failed to retrieve diagram page, skipping. url: {category_page_url}')
                category_page_link['done'] = True
                category_page_link['skipped'] = True
                continue
            
            additional_vars = {
                'base_car_url': url,
                'category_page_url': category_page_url
            }

            diagrams, part_list = self.cached_parser.parse_cached_page(diagram_page_source, PageType.DIAGRAMS, additional_vars, diagrams_cached)

            # Save diagram images
            for diagram in diagrams['diagrams']:
                img_name = diagram['img']
                if not img_name in images and img_name != '':
                    image_url = 'https:' + diagram['img_url'] if 'https' not in diagram['img_url'] else diagram['img_url']
                    saved, uploaded = self.save_image(image_url, img_name)
                    images[img_name] = {'url': image_url, 'alt': diagram['alt_text'], 'saved': saved, 'uploaded': uploaded}


            engine[keys.DIAGRAMS].append(diagrams)

            # Loop through all the parts and see which ones we need to scrape. Also populate the car's parts list
            for part in part_list:
                part_number = part
                if part_number not in parts:
                    parts_to_scrape.append({'part_number': part, 'url': part_list[part]})
                if part_number not in engine[keys.PARTS]:
                    engine[keys.PARTS].append(part_number)

            for part in parts_to_scrape:
                part_number = part[keys.PART_NUMBER]
                part_page_url = part['url']

                if part_number in parts:
                    print('Skipping already scraped part: ' + part_number)
                    continue
                
                try:
                    part_page_source, part_cached = self.get_and_cache_page_source(part_page_url, browser_util)
                except PageRetrievalError:
                    print('Page Retrieval error caught, skip this part')
                    parts[part_number] = {
                        'title': '',
                        'part_number': part_number,
                        'url': part_page_url,
                        'images': [],
                        'details': {},
                        'fitment': [],
                        'skipped': True
                    }
                    continue

                print('Scraping part number: ' + part_number + ' Cached: ' + str(part_cached))

                part_data = self.cached_parser.parse_cached_page(part_page_source, PageType.PART)
                part_data['url'] = part['url']

                parts[part_number] = part_data

                # Save part images
                for part_image_rec in part_data['images']:
                    for img_cat in ['main', 'preview', 'thumb']:
                        if not part_image_rec[img_cat]:
                            continue
                        part_img_url = 'https:' + part_image_rec[img_cat]['url'] if 'https' not in part_image_rec[img_cat]['url'] else part_image_rec[img_cat]['url']
                        part_img_name = self.get_image_name(part_img_url)

                        if not part_img_name in images:
                            saved, uploaded = self.save_image(part_img_url, part_img_name)
                            images[part_img_name] = {'url': part_img_url, 'alt': None, 'saved': saved, 'uploaded': uploaded}

            category_page_link['done'] = True
        browser_util.close()