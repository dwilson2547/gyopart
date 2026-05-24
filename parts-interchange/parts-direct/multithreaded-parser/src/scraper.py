
from enum import Enum
import logging
import threading
import time
import queue
import os

from .utils.queue_request import QueueRequest, QueueRequestType, InvalidQueueTypeException
from .utils.config import Config
from .utils.constants import CommonKeys, INFLUX_MEASURE, PageType
from .utils.browser_util import BrowserUtil
from .utils.cached_parser import CachedParser
from .utils.browser_cache import BrowserCache
from .utils.bucket_utils import BucketUtils
from .utils.influx_utils import InfluxUtils
from .utils.save_load import SaveLoad

from .threads.browser_thread import browser_queue_thread
from .threads.images_thread import images_queue_thread
from .threads.parts_thread import parts_queue_thread

log = logging.getLogger(__name__)

class PartsDirectParser:

    browser_util = None
    cached_parser = None
    browser_cache = None
    bucket_utils = None
    influx_utils = None
    instance_name = None
    save_load = None

    browser_queue = queue.Queue()
    image_queue = queue.Queue()
    part_queue = queue.Queue()

    def start(self, config_name: str, instance_name: str):
        cfg = Config(config_name)
        self.cfg = cfg
        self.browser_util = BrowserUtil(cfg)
        self.cached_parser = CachedParser(cfg.BASE_URL)
        self.browser_cache = BrowserCache(cfg)
        self.bucket_utils = BucketUtils(cfg)
        self.influx_utils = InfluxUtils(instance_name, cfg)
        self.save_load = SaveLoad(cfg, self.bucket_utils, self.browser_cache)
        self.instance_name = instance_name


    def traverse_tree(self, tree: dict, parts: dict, images: dict):
        try:
            for yr, year in tree.items():
                for mk, make in year[CommonKeys.MAKES].items():
                    for mdl, model in make[CommonKeys.MODELS].items():
                        for trm, trim in model[CommonKeys.TRIMS].items():
                            for eng, engine in trim[CommonKeys.ENGINES].items():
                                if 'done' in engine and engine['done']:
                                    continue
                                elif 'part_skip' in engine and engine['part_skip']:
                                    engine['done'] = True
                                    continue
                                else:
                                    engine['done'] = False
                                log.info(self.influx_utils.get_influx_stats(yr, mk, mdl, trm, eng))
                                self.influx_utils.post_point(INFLUX_MEASURE, self.influx_utils.get_tags(), self.influx_utils.get_influx_stats(yr, mk, mdl, trm, eng))
                                url = engine[CommonKeys.PAGE_URL]
                                self.process_car_data(url, engine, parts, images)
                                engine['done'] = True
                                self.save(tree, parts, images, low_priority_save=True)

        except Exception as ex:
            log.error(str(ex))

    def process_car_data(self, url, engine, parts, images):

        # Init part and diagram arrays, clean up legacy property categories
        if 'categories' in engine:
            engine.pop('categories')
        if CommonKeys.PARTS not in engine:
            engine[CommonKeys.PARTS] = []
        if CommonKeys.DIAGRAMS not in engine:
            engine[CommonKeys.DIAGRAMS] = []

        # Init browser
        browser_util = self.browser_util

        # Retreive list of category links and add it to the engine record
        if CommonKeys.CATEGORY_LINKS not in engine:
            try:
                categories_page_source, cats_cached = self.get_and_cache_page_source(url, browser_util)
            except PageRetrievalError as ex:
                print(f'Failed to retrieve categories page, skipping. url: {url}')
                engine[CommonKeys.CATEGORY_LINKS] = []
                engine['skipped'] = True
                return

            print('Parsing categories. Cached: ' + str(cats_cached))
            engine[CommonKeys.CATEGORY_LINKS] = self.cached_parser.parse_category_page(categories_page_source)

        # Loop through category links and build diagrams. Start list of parts that need to be scraped so we can get those next
        for category_page_link in engine[CommonKeys.CATEGORY_LINKS]:

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

            diagrams, part_list = self.cached_parser.parse_diagram_page(diagram_page_source, additional_vars, diagrams_cached)

            # Save diagram images
            for diagram in diagrams['diagrams']:
                img_name = diagram['img']
                if not img_name in images and img_name != '':
                    image_url = 'https:' + diagram['img_url'] if 'https' not in diagram['img_url'] else diagram['img_url']
                    saved, uploaded = self.save_image(image_url, img_name)
                    images[img_name] = {'url': image_url, 'alt': diagram['alt_text'], 'saved': saved, 'uploaded': uploaded}


            engine[CommonKeys.DIAGRAMS].append(diagrams)

            # Loop through all the parts and see which ones we need to scrape. Also populate the car's parts list
            for part in part_list:
                part_number = part
                if part_number not in parts:
                    parts_to_scrape.append({'part_number': part, 'url': part_list[part]})
                if part_number not in engine[CommonKeys.PARTS]:
                    engine[CommonKeys.PARTS].append(part_number)

            for part in parts_to_scrape:
                part_number = part[CommonKeys.PART_NUMBER]
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

                part_data = self.cached_parser.parse_part(part_page_source)
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


        

q = queue.Queue()

def thread_function(name):
    logging.info("Thread %s: starting", name)
    r = queue.Queue()
    payload = {
        'name': f'thread-{name}',
        'queue': r
    }
    q.put(payload)
    resp = r.get()
    print(resp)
    time.sleep(2)
    logging.info("Thread %s: finishing", name)

def queue_reader():
    while True:
        item = q.get()
        logging.info("queue %s: starting", item['name'])
        time.sleep(2)
        logging.info("queue %s: finishing", item['name'])
        q.task_done()
        item['queue'].put('queue-finished ' + item['name'])

if __name__ == "__main__":
    format = "%(asctime)s: %(message)s"
    logging.basicConfig(format=format, level=logging.INFO,
                        datefmt="%H:%M:%S")

    threading.Thread(target=queue_reader, daemon=True).start()

    threads = list()
    for index in range(3):
        logging.info("Main    : create and start thread %d.", index)
        x = threading.Thread(target=thread_function, args=(index,))
        threads.append(x)
        x.start()

    for index, thread in enumerate(threads):
        logging.info("Main    : before joining thread %d.", index)
        thread.join()
        logging.info("Main    : thread %d done", index)

    q.join()