import bz2
import json
import os
import shutil
import uuid

from utils.BucketUtils import BucketUtils
from utils.Constants import BUCKET_NAME, SaveFiles


class BrowserCache:

    cache = {}

    def __init__(self, config_name, base_dir, secondary_lookup_dir: str = None):
        """
        BrowserCache module, used to save a local copy of webpages visited so they can be loaded later. Page data is stored under {base_dir}/webcache/* and the main cache is stored 
        at {base_dir}/webcache.json. A secondary lookup location can be provided if you have data split across two directories.
        :param config_name, str, manufacturer name, needed in case we have to do a bucket dump
        :param base_dir: str
        :param secondary_lookup_dir: str, optional secondary location for page files
        """
        self.config_name = config_name
        self.base_dir = base_dir
        self.data_dir = os.path.join(base_dir, SaveFiles.WEBCACHE_DIR)
        self.webcache_file = os.path.join(self.base_dir, SaveFiles.WEBCACHE_FILE)
        self.backup_dir = os.path.join(self.base_dir, SaveFiles.BACKUPS_DIR)
        self.backup_webcache_file = os.path.join(self.backup_dir, SaveFiles.WEBCACHE_FILE)
        if not os.path.exists(self.data_dir):
            os.mkdir(self.data_dir)
        if not os.path.exists(self.backup_dir):
            os.mkdir(self.backup_dir)
        
        self.cache = self._load()
        # Turns out, saving a copy of every web page visited takes up a lot of space and not all files can be stored 
        # locally. Add this dir with any extra cached files that were migrated off to nas or some other location
        # In hindsight, I should've started with bz2 files but better late than never
        self.secondary_lookup_dir = secondary_lookup_dir if secondary_lookup_dir else ''

    def add_to_cache(self, page_url, page_text):
        """
        Cleans the provided page url and creates a uuid name from it which becomes the filename along with the bz2 extension. Saves page text within the data directory and adds url: filename record to hashmap

        :param page_url: str, url of page
        :param page_text: str, raw html dump of page
        """
        clean_url = self.get_clean_url(page_url)
        file_name = str(uuid.uuid5(uuid.NAMESPACE_URL, clean_url)) + '.bz2'

        with bz2.open(os.path.join(self.data_dir, file_name), 'wt') as f:
            f.write(page_text)

        self.cache[clean_url] = file_name

    def remove_from_cache(self, page_url):
        clean_url = self.get_clean_url(page_url)
        path = os.path.join(self.data_dir, self.cache[clean_url])
        if os.path.exists(path):
            os.remove(path)
        self.cache.pop(clean_url)
    
    def save(self):
        """
        Saves main cache hashmap to default location, {base_dir}/webcache.json
        """

        with open(self.webcache_file, 'w') as f:
            f.write(json.dumps(self.cache))

        shutil.copyfile(self.webcache_file, self.backup_webcache_file)

    def bucket_save(self, bucketUtil: BucketUtils):
        """
        Last ditch effort to save data when everything else fails. This will dump the main cache hashmap to the bucket as a json file

        :param bucketUtil: BucketUtils
        """
        bucketUtil.dump_json_to_bucket(BUCKET_NAME, self.config_name, SaveFiles.WEBCACHE_FILE, self.cache)

    def _load(self):
        """
        Loads from webcache save file, checks new default location, {base_dir}/webcache.json and the legacy location {data_dir}/webcache.json. If no
        file is found, assumes a new run and returns an empty dictionary.
        """
        if not os.path.exists(self.webcache_file):
            print('webcache file not found in default location, checking legacy location')
            legacy_path = os.path.join(self.data_dir, SaveFiles.WEBCACHE_FILE)
            if not os.path.exists(legacy_path):
                print('webcache file not found in legacy location either, assuming new run')
                return {}
            
            with open(legacy_path) as f:
                return json.load(f)
            
        with open(self.webcache_file) as f:
            return json.load(f)
        
    def page_exists_in_cache(self, url):
        """
        Check whether the provided url has been cached already. Will check cache hashmap and local filesystem to try and find cached data. If found returns true, otherwise false
        :param url, str
        :return: bool, url found or not (t and f respectively)
        """
        clean_url = self.get_clean_url(url)
        if clean_url in self.cache:
            if os.path.exists(os.path.join(self.data_dir, self.cache[clean_url])):
                return True
            else:
                return False
        else:
            file_name = str(uuid.uuid5(uuid.NAMESPACE_URL, clean_url))

            html_path = os.path.join(self.data_dir, file_name + '.html')
            bz2_path = os.path.join(self.data_dir, file_name + '.bz2')
            
            if os.path.exists(html_path):
                self.cache[clean_url] = file_name + '.html'
                return True
            if os.path.exists(bz2_path):
                self.cache[clean_url] = file_name + '.bz2'
                return True
            
            return False
        
    def get_cached_page(self, url):
        """
        Retrieves page text from a locally cached page, url is cleaned and then checked against the cache hashmap. Checks both the primary and secondary locations.

        :param url: str
        :return: str, raw text of webpage
        """
        f_name = self.cache[self.get_clean_url(url)]

        primary_loc = os.path.join(self.data_dir, f_name)
        secondary_loc = os.path.join(self.secondary_lookup_dir, f_name)
        if os.path.exists(primary_loc):
            raw_html = self._read_file(primary_loc)
        elif os.path.exists(secondary_loc):
            raw_html = self._read_file(secondary_loc)

        return raw_html

    def _read_file(self, file_path):
        """
        Opens text file at provided path and returns the text. Will use default file reader if extension is html, otherwize it uses bz2 reader

        :param file_path: str
        :return: str, file text
        """
        if '.html' in file_path:
            with open(file_path) as f:
                return f.read()
        else:
            with bz2.open(file_path, 'rt') as f:
                return f.read()
    
    def get_clean_url(self, url):
        """
        Strips any query parameters from a url and return it
        :param url: str
        :return: str: url lol
        """
        return url.split('?')[0]
