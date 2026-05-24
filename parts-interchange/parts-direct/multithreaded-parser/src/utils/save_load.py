import json
import sys
from .constants import BUCKET_NAME, SaveFiles
from .config import Config
from .bucket_utils import BucketUtils
from .browser_cache import BrowserCache
from datetime import datetime as dt
import logging
import shutil
import os

log = logging.getLogger(__name__)

class SaveLoad:

    def __init__(self, cfg: Config, bucket_utils: BucketUtils, browser_cache: BrowserCache):
        self.cfg = cfg
        self.bucket_utils = bucket_utils
        self.browser_cache = browser_cache
        self.save_time = 0

    def load(self):
        log.info('loading...')
        tree = None
        parts = None
        images = None
        try:
            with open(self.cfg.TREE_FILE) as tf:
                tree = json.load(tf)
        except Exception:
            print('Loading failed, assuming new run')
        try:
            with open(self.cfg.PARTS_FILE) as pf:
                parts = json.load(pf)
        except Exception:
            pass
        try:
            with open(self.cfg.IMAGES_FILE) as imgf:
                images = json.load(imgf)
        except Exception:
            pass
        log.info('done')
        return tree, parts, images

    def save(self, tree, parts, images, fresh_run = False, low_priority_save = False):

        curr_time = dt.now().timestamp()
        if curr_time - self.save_time < 1800 and low_priority_save:
            log.info('low priority save, skipping')
            return

        try:
            log.info('saving...')
            if tree:
                with open(self.cfg.TREE_FILE, 'w') as tf:
                    tf.write(json.dumps(tree))
                if fresh_run:
                    with open(self.cfg.BLANK_TREE, 'w') as btf:
                        btf.write(json.dumps(tree))
            if parts:
                with open(self.cfg.PARTS_FILE, 'w') as pf:
                    pf.write(json.dumps(parts))
            if images:
                with open(self.cfg.IMAGES_FILE, 'w') as imgf:
                    imgf.write(json.dumps(images))
            self.browser_cache.save()
            self.create_backups()
            self.save_time = curr_time
            log.info('finished')
        except KeyboardInterrupt:
            print('Saving now, try again once finished.')
            self.save(tree, parts, images)
        except Exception as ex:
            log.error(ex)
            log.warn('Failed to save in default directory, saving to bucket and then killing process')
            try:
                self.bucket_utils.dump_json_to_bucket(BUCKET_NAME, self.cfg.config_name, SaveFiles.TREE_FILE, tree)
                self.bucket_utils.dump_json_to_bucket(BUCKET_NAME, self.cfg.config_name, SaveFiles.PARTS_FILE, parts)
                self.bucket_utils.dump_json_to_bucket(BUCKET_NAME, self.cfg.config_name, SaveFiles.IMAGES_FILE, images)
                self.browser_cache.bucket_save(self.bucket_utils)
            except Exception:
                log.error('Failed to save to bucket, ending process')
                sys.exit(0)

            log.info('Bucket save complete, ending process')

            sys.exit(0)

    def create_backups(self):
        try:
            shutil.copyfile(self.cfg.TREE_FILE, self.cfg.BACKUP_TREE_FILE)
            if os.path.exists(self.cfg.IMAGES_FILE):
                shutil.copyfile(self.cfg.IMAGES_FILE, self.cfg.BACKUP_IMAGES_FILE)
            if os.path.exists(self.cfg.PARTS_FILE):
                shutil.copyfile(self.cfg.PARTS_FILE, self.cfg.BACKUP_PARTS_FILE)
        except Exception:
            log.error('Creating backups failed, exiting now')
            sys.exit(0)
