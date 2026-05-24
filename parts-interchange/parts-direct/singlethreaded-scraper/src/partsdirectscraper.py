import copy
import json
import os
import time
import urllib.request
from datetime import datetime

from utils.InfluxUtils import InfluxUtils
from utils.BucketUtils import BucketUtils
from utils.BrowserCache import BrowserCache

from utils.Constants import Steps, keys
from utils.Exceptions import NoProgressException

from bs4 import BeautifulSoup as bs
from minio import Minio
from requests_html import HTMLSession
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.remote.webelement import WebElement
from urllib3 import encode_multipart_formdata
from webdriver_manager.chrome import ChromeDriverManager


def format_print_msg(message, level = 0):
    print('    ' * level + message)

def build_form(step: str, year: str, make: str = None, model: str = None, trim: str = None):
    time.sleep(3.5)
    form = {
        "type": "get_next_json",
        "step": step,
        "picker_type": "normal",
        "selected[year]": year
    }
    if make:
        form["selected[make]"] = make
    if model:
        form["selected[model]"] = model
    if trim:
        form["selected[trim]"] = trim
    return form

class PartsDirectScraper:

    BASE_URL = ''
    ALL_MAKES_URL = ''
    PICKER_AJAX_URL = ''
    INFLUX_MEASURE = 'scraper_status'
    BUCKET_NAME = 'part-images'
    DATA_DIR = ''
    PARTS_FILE = ''
    IMG_DIR = ''
    IMAGES_FILE = ''
    TREE_FILE = ''
    DEBUG_PORT = ''

    browser_cache: BrowserCache

    save_timestamp = 0
    influx_utils: InfluxUtils = None

    def __init__(self, base_url, instance_name, data_dir, debug_port, config_name):
        self.BASE_URL = base_url
        self.DATA_DIR = data_dir
        self.DEBUG_PORT = debug_port
        self.config_name = config_name

        self.ALL_MAKES_URL = f'{self.BASE_URL}/ajax/vehicle-picker/makes/all'
        self.PICKER_AJAX_URL = f'{self.BASE_URL}/ajax/vehicle-picker/next'
        self.PARTS_FILE = os.path.join(self.DATA_DIR, 'parts.json')
        self.IMG_DIR = os.path.join(self.DATA_DIR, 'images')
        self.IMAGES_FILE = os.path.join(self.DATA_DIR, 'imgs.json')
        self.TREE_FILE = os.path.join(self.DATA_DIR, 'tree.json')

        self.save_timestamp = datetime.now().timestamp()

        if not os.path.exists(self.DATA_DIR):
            os.mkdir(self.DATA_DIR)
        if not os.path.exists(self.IMG_DIR):
            os.mkdir(self.IMG_DIR)

        self.influx_utils = InfluxUtils(instance=instance_name)
        self.bucket_utils = BucketUtils()
        self.browser_cache = BrowserCache(config_name, data_dir)

    def build_car_url(self, year, make, model, trim, engine):
        return self.BASE_URL + f'/v-{year}-{make}-{model}--{trim}--{engine}'

    def load(self):
        tree = None
        parts = None
        images = None
        try:
            with open(self.TREE_FILE) as tf:
                tree = json.load(tf)
        except:
            print('Loading failed, assuming new run')
            return None, None, None
        
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

    def save(self, tree, parts, images):
        try:
            print('saving...')
            if tree:
                with open(self.TREE_FILE, 'w') as tf:
                    tf.write(json.dumps(tree))
            if parts:
                with open(self.PARTS_FILE, 'w') as pf:
                    pf.write(json.dumps(parts))
            if images:
                with open(self.IMAGES_FILE, 'w') as imgf:
                    imgf.write(json.dumps(images))
            self.browser_cache.save()
            print('finished')
        except KeyboardInterrupt:
            print('Saving now, try again once finished.')
            self.save(tree, parts, images)
        except Exception:
            print('Failed to save in default directory, saving to instance root dir')
            with open('temp_outfile.json', 'w') as f:
                f.write(json.dumps({
                    'tree': tree,
                    'parts': parts,
                    'images': images
                }))
            raise NoProgressException('Save location is misconfigured')

    def scrape_car_list(self):
        session = HTMLSession()

        tree, parts, images = self.load()

        if not parts:
            parts = {}
        if not images:
            images = {}

        if not tree:
            tree = {}
            resp = session.get(self.ALL_MAKES_URL).json()
            for make in resp:
                # For some reason they give us makes with start and end years
                # even though the picker works in the opposite direction...
                # So we have to build the year list and start the tree there 
                # and add the make to each year record in the tree
                year_range = list(range(make['start_year'], make['end_year'] + 1))
                for year in year_range:
                    if str(year) not in tree:
                        tree[str(year)] = {
                            'makes': {}
                        }
                    if make['url'] not in tree[str(year)][keys.MAKES]:
                        make[keys.MODELS] = {}
                        tree[str(year)][keys.MAKES][make['url']] = copy.deepcopy(make)
                
            # Now we can continue on to getting the other options, starting with models
            for year in tree:
                format_print_msg(year)
                for m in tree[year][keys.MAKES]:
                    make = tree[year][keys.MAKES][m]
                    format_print_msg(make['ui'], 1)

                    model_form = build_form(Steps.MODEL, year, make['url'])
                    body, header = encode_multipart_formdata(fields=model_form)
                    models = session.post(self.PICKER_AJAX_URL, data=body, headers={'Content-Type': header}).json()
                    for model in models:
                        format_print_msg(model['ui'], 2)
                        model[keys.TRIMS] = {}
                        make[keys.MODELS][model['url']] = model

                        # Then trims
                        trim_form = build_form(Steps.TRIM, year, make['url'], model['url'])
                        trim_body, trim_header = encode_multipart_formdata(fields=trim_form)
                        trims = session.post(self.PICKER_AJAX_URL, data=trim_body, headers={'Content-Type': trim_header}).json()
                        for trim in trims:
                            format_print_msg(trim['ui'], 3)
                            trim[keys.ENGINES] = {}
                            model[keys.TRIMS][trim['url']] = trim

                            # And finally engines
                            engine_form = build_form(Steps.ENGINE, year, make['url'], model['url'], trim['url'])
                            engine_body, engine_header = encode_multipart_formdata(fields=engine_form)
                            engines = session.post(self.PICKER_AJAX_URL, data=engine_body, headers={'Content-Type': engine_header}).json()
                            for engine in engines:
                                format_print_msg(engine['ui'], 4)
                                engine[keys.CATEGORIES] = {}
                                # Build the url for the categories page
                                engine[keys.PAGE_URL] = self.build_car_url(year, make['url'], model['url'], trim['url'], engine['url'])
                                trim[keys.ENGINES][engine['url']] = engine

            self.save(tree, parts, images)
        self.scrape_parts(tree, parts, images)

    def get_file_name(self, url: str):
        return url.split('/')[-1]

    def save_image(self, url, file_name):
        time.sleep(2)
        file_path = os.path.join(self.IMG_DIR, file_name)

        try:
            urllib.request.urlretrieve(url, file_path)
        except:
            print('Failed to save image at url: ' + url)
            return False, False
        
        try:
            self.bucket_utils.upload_image_to_bucket(self.BUCKET_NAME, self.config_name, file_name, file_path)
        except Exception as ex:
            print('Failed to upload image to bucket')
            print(ex)
            return True, False
        
        return True, True

    def click_link(self, link):
        time.sleep(3.5)
        link.click()

    def browser_navigate(self, browser, location):
        time.sleep(3.5)
        browser.get(location)
        ps = browser.page_source
        self.browser_cache.add_to_cache(location, ps)

    def autosave(self, tree, parts, images):
        delta = datetime.now().timestamp() - self.save_timestamp
        if delta > 1800:
            self.save(tree, parts, images)
            self.save_timestamp = datetime.now().timestamp()

    def get_influx_stats(self, yr, mk, mdl, trm, eng, status=True):
        return {
            'year': yr, 
            'make': mk,
            'model': mdl,
            'trim': trm,
            'engine': eng,
            'status': 'running' if status else 'dead'
        }

    def scrape_parts(self, tree, parts, images):
        # Drill down to where the car page urls are saved
        progress = False
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
                                print(self.get_influx_stats(yr, mk, mdl, trm, eng))
                                self.influx_utils.post_point(self.INFLUX_MEASURE, self.influx_utils.get_tags(), self.get_influx_stats(yr, mk, mdl, trm, eng))
                                url = engine[keys.PAGE_URL]
                                self.process_car_data(url, engine, parts, images)
                                progress = True
                                engine['done'] = True
                                self.save(tree, parts, images)
        except Exception as ex:
            self.save(tree, parts, images)
            if not progress:
                self.influx_utils.post_point(self.INFLUX_MEASURE, self.influx_utils.get_tags(), self.get_influx_stats(yr, mk, mdl, trm, eng, False))
                raise NoProgressException(ex)
            raise ex
        except KeyboardInterrupt:
            self.save(tree, parts, images)
            raise NoProgressException('Keyboard Interrupt Caught')

    def process_car_data(self, url, engine, parts, images):
        """
        Retrieves a list of categories for this config, then visits each page. The pages contain diagrams
        with part numbers and part links. This saves the part diagrams with their images and part number mappings, 
        then checks for any already scanned parts. If the part has been scraped already, we just add it to a list of
        parts for this config and continue. For any parts that haven't been scraped yet, this calls the scrape_part_metadata
        function to add that part to the index.
        """
        PART_FILTER_SELECTOR = '.oem-sidebar-categories a.cat-autoparts'
        # SUBCATEGORY_LINKS_SELECTOR = 'div.oem-sidebar-categories div.category-parts div.card.parts div.subcategories-list a'
        SUBCATEGORY_LINKS_SELECTOR = 'div.oem-sidebar-categories div.category-parts div.card.parts a'
        PART_SELECTOR = '.product-title a'

        PART_CATEGORY_SELECTOR = '.page-bread-crumbs a:nth-of-type(3)'

        if 'categories' in engine:
            engine.pop('categories')
        if keys.PARTS not in engine:
            engine[keys.PARTS] = []
        if keys.DIAGRAMS not in engine:
            engine[keys.DIAGRAMS] = []
        
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        # options.add_argument('--no-sandbox')
        # options.add_argument('--proxy-server=socks5://127.0.0.1:9050')
        options.add_argument("--remote-debugging-port="+self.DEBUG_PORT)

        browser = webdriver.Chrome(ChromeDriverManager().install(), options=options)
        browser.implicitly_wait(10)

        if 'cat_links' not in engine:
            self.browser_navigate(browser, url)

            # Clicking this link hides the accessory items
            try:
                browser.implicitly_wait(2)
                part_filter_link = browser.find_element(By.CSS_SELECTOR, PART_FILTER_SELECTOR)
                browser.implicitly_wait(10)
            except Exception as ex:
                print(ex)
                print('Failed to get parts category filter, skipping this config')
                engine['part_skip'] = True
                browser.close()
                return

            self.click_link(part_filter_link)

            # Get list of part sub categories
            sub_category_links = browser.find_elements(By.CSS_SELECTOR, SUBCATEGORY_LINKS_SELECTOR)

            # Extract urls to avoid stale references later on
            engine['cat_links'] = [x.get_property('href') for x in sub_category_links]
            engine['cat_links'] = [{ 'url': x, 'done': False } for x in engine['cat_links'] if x.split(self.BASE_URL + '/')[1][0] != '#']

        for entry in engine['cat_links']:
            if entry['done']:
                continue
            link = entry['url']
            self.browser_navigate(browser, link)

            # Get current subcategory name so we can use it for metadata with diagrams
            try:
                sub_cat_name = browser.find_element(By.CSS_SELECTOR, PART_CATEGORY_SELECTOR).text
            except:
                print('Failed to get sub category for link:')
                print(link)
                entry['done'] = True
                entry['skipped'] = True
                continue

            # List to store the urls we need to visit later on
            parts_to_scrape = []

            # Breaks the page down into groups of parts by diagram, from each group we can 
            # extract the image and part number mappings
            groups = browser.find_elements(By.CSS_SELECTOR, 'div.part-group-container')
            
            print('Building diagrams for category: ' + sub_cat_name)
            for i, group in enumerate(groups):

                # The last group has a header titled related parts
                if i + 1 == len(groups):
                    try:
                        group.find_element(By.CSS_SELECTOR, 'h2.related_parts')

                        part_rows = group.find_elements(By.CSS_SELECTOR, '.all-parts-table-container .catalog-product')

                        for row in part_rows:
                            # Get the part number link
                            part_number_link = row.find_element(By.CSS_SELECTOR, '.product-details-col .product-partnum a')
                            # Extract part number
                            part_number = part_number_link.text.strip()
                            # Check if part number has already been scraped
                            if part_number in parts:
                                print('Skipping already scraped part: ' + part_number)
                                # Already been scraped
                                if part_number not in engine[keys.PARTS]:
                                    engine[keys.PARTS].append(part_number)
                                continue
                            # Otherwise, save this url and part number so we can scrape them and add them to the list too
                            else:
                                parts_to_scrape.append({'part_number': part_number, 'url': part_number_link.get_property('href')})

                        continue
                    except:
                        pass

                # Get diagram image and metadata
                try:
                    part_diagram_img = group.find_element(By.CSS_SELECTOR, 'img.parts-diagram')
                except Exception as ex:
                    print(ex)
                    print('Part diagram not found, skipping')
                    continue
                part_diagram_url = part_diagram_img.get_property('src')
                part_diagram_name = self.get_file_name(part_diagram_url)
                
                # Save the image if it hasn't been saved yet
                if part_diagram_name not in images:
                    saved, uploaded = self.save_image(part_diagram_url, part_diagram_name)
                    images[part_diagram_name] = {'url': part_diagram_url, 'alt': part_diagram_img.get_property('alt'), 'saved': saved, 'uploaded': uploaded}

                # Build diagram object
                diagram = {
                    'img': part_diagram_name,
                    'category_name': sub_cat_name,
                    'base_car_url': url,
                    'category_url': link,
                    'parts': {}
                }

                # Retrieve part rows
                part_rows = group.find_elements(By.CSS_SELECTOR, '.all-parts-table-container .catalog-product')

                for row in part_rows:
                    # Reference code is the key that maps to the diagram image
                    diagram_reference_code =  row.find_element(By.CSS_SELECTOR, '.reference-code-col').text
                    # Get the part number link
                    part_number_link = row.find_element(By.CSS_SELECTOR, '.product-details-col .product-partnum a')
                    # Extract part number
                    part_number = part_number_link.text.strip()
                    # Save reference code to part number mapping
                    diagram['parts'][diagram_reference_code] = part_number
                    # Check if part number has already been scraped
                    if part_number in parts:

                        # Had a snafu with a bunch of titles going missing, this should allow for filling in most of 
                        # the titles without having to re-scrape pages
                        if not parts[part_number]['title']:

                            # Get the part number link
                            part_title_link = row.find_element(By.CSS_SELECTOR, '.product-details-col .product-title a')
                            # Extract part number
                            part_title = part_title_link.text.strip()

                            parts[part_number]['title'] = part_title
                        
                        if 'url' not in parts[part_number]:
                            parts[part_number]['url'] = part_number_link.get_property('href')

                        if not parts[part_number]['url']:
                            parts[part_number]['url'] = part_number_link.get_property('href')

                        print('Skipping already scraped part: ' + part_number)
                        # Already been scraped 
                        if part_number not in engine[keys.PARTS]:
                            engine[keys.PARTS].append(part_number)
                        continue
                    # Otherwise, save this url and part number so we can scrape them and add them to the list too
                    else:
                        parts_to_scrape.append({'part_number': part_number, 'url': part_number_link.get_property('href')})
                
                engine[keys.DIAGRAMS].append(diagram)

            # Time to scrape some parts
            for part_record in parts_to_scrape:
                part_number = part_record['part_number']
                if part_number in parts:
                    print('Skipping already scraped part: ' + part_number)
                    continue
                self.browser_navigate(browser, part_record['url'])
                print('Scraping part number: ' + part_number)
                part = self.scrape_part_metadata(browser, images)
                part['url'] = part_record['url']
                if part_number in parts:
                    print('oops')
                parts[part_number] = part
                if part_number not in engine[keys.PARTS]:
                    engine[keys.PARTS].append(part_number)
                # TODO: Loop through fitments and add part to other vehicles

            # Cleanup time
            parts_to_scrape = []
            entry['done'] = True

        browser.close()

    def scrape_part_metadata(self, browser: webdriver.Chrome, images):
        """
        This function creates a part object for the current browser page. It finds the product images and saves them, 
        then gets the product details and fitment table. Then returns the part
        """
        PART_NAME_SELECTOR = 'div.product-title-module h1'
        PART_DETAILS_SELECTOR = 'div.product-details-module ul.field-list li'
        PART_FITMENT_SELECTOR = 'table.fitment-table'

        # Get title
        try:
            titles = browser.find_elements(By.CSS_SELECTOR, PART_NAME_SELECTOR)
        except NoSuchElementException:
            # Part page not found, mark as skip and save url
            print('Failed to find page header, skipping part')
            return {
                    'title': 'skipped',
                    'images': [],
                    'details': {},
                    'fitment': []
                }
        
        # Search for a title that has text, sometimes mobile title comes before desktop
        title = None
        for item in titles:
            if item.text.strip() != '':
                title = item.text.strip()

        # Base part structure
        part = {
            'title': title,
            'images': [],
            'details': {},
            'fitment': []
        }

        # Add images and associated metadata, change wait for images to 1 second so we don't waste a bunch of time trying to find something
        # that isn't there
        browser.implicitly_wait(1)
        part_image_links = browser.find_elements(By.CSS_SELECTOR, '.desktop-only div.product-images-module a img')
        if not part_image_links:
            part_image_links = browser.find_elements(By.CSS_SELECTOR, 'div.product-images-module a img')
        browser.implicitly_wait(10)

        # Get all images for this part, download them if necessary, then add them to the part
        for link in part_image_links:
            image_url = link.get_attribute('data-image-main-url')
            if not image_url:
                image_url = link.get_attribute('src')
            caption = link.get_attribute('data-caption')
            if not caption:
                caption = link.get_attribute('alt')
            img_type = link.get_attribute('data-image-type')
            id = link.get_attribute('data-image-id')
            img_name = self.get_file_name(image_url)
            if img_name not in images:
                saved, uploaded = self.save_image(image_url, img_name)
                images[img_name] = {'url': image_url, 'alt': title, 'saved': saved, 'uploaded': uploaded}
            part['images'].append({
                'img': img_name,
                'caption': caption,
                'type': img_type,
                'vendor_id': id
            })
        
        # Get details
        detail_rows = browser.find_elements(By.CSS_SELECTOR, PART_DETAILS_SELECTOR)
        for row in detail_rows:
            kvp = row.text.split(':')
            if kvp[0] == 'Genuine':
                continue
            if len(kvp) == 2:
                part['details'][kvp[0].strip()] = kvp[1].strip()
            elif len(kvp) > 2:
                key = kvp.pop(0)
                value = ':'.join(kvp)
                part['details'][key] = value
            
        # Get Fitment table
        try:
            table = browser.find_element(By.CSS_SELECTOR, PART_FITMENT_SELECTOR)
        except:
            table = None

        if table:
            # Parse table with beautiful soup, it's faster this way
            soup = bs(table.get_attribute('outerHTML'), 'html.parser')
            rows = soup.find('tbody').find_all('tr', {'class': 'fitment-row'})
            for row in rows:
                year = row.find('td', {'class': 'fitment-year'}).text.strip()
                make = row.find('td', {'class': 'fitment-make'}).text.strip()
                model = row.find('td', {'class': 'fitment-model'}).text.strip()
                trims = row.find('td', {'class': 'fitment-trim'}).text.strip().split(',')
                trims = [x.strip() for x in trims]
                engines = row.find('td', {'class': 'fitment-engine'}).text.strip().split(',')
                engines = [x.strip() for x in engines]
                part['fitment'].append({
                    'year': year,
                    'make': make,
                    'model': model,
                    'trims': trims,
                    'engines': engines
                })
        
        return part

