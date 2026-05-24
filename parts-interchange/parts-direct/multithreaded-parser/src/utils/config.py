import os

from .constants import SaveFiles
from .scraper_configs import ScraperConfigs


class Config:

    def __init__(self, config_name):
        cfg = ScraperConfigs.get(config_name)

        self.BASE_URL = cfg['base_url']
        self.DATA_DIR = cfg['data_dir']
        self.DEBUG_PORT = cfg['port']
        self.config_name = config_name
        self.page_request_delay = 3.5

        self.PARTS_FILE = os.path.join(self.DATA_DIR, SaveFiles.PARTS_FILE)
        self.IMG_DIR = os.path.join(self.DATA_DIR, SaveFiles.IMAGES_DIR)
        self.IMAGES_FILE = os.path.join(self.DATA_DIR, SaveFiles.IMAGES_FILE)
        self.TREE_FILE = os.path.join(self.DATA_DIR, SaveFiles.TREE_FILE)
        self.BLANK_TREE = os.path.join(self.DATA_DIR, SaveFiles.BLANK_TREE_FILE)

        self.BACKUPS_DIR = os.path.join(self.DATA_DIR, SaveFiles.BACKUPS_DIR)
        self.BACKUP_TREE_FILE = os.path.join(self.BACKUPS_DIR, SaveFiles.TREE_FILE)
        self.BACKUP_IMAGES_FILE = os.path.join(self.BACKUPS_DIR, SaveFiles.IMAGES_FILE)
        self.BACKUP_PARTS_FILE = os.path.join(self.BACKUPS_DIR, SaveFiles.PARTS_FILE)

        self.bucket_url = os.getenv('BUCKET_URL')
        self.bucket_access = os.getenv('BUCKET_ACCESS')
        self.bucket_secret = os.getenv('BUCKET_SECRET')

        self.influx_bucket = os.getenv('INFLUX_BUCKET')
        self.influx_org = os.getenv('INFLUX_ORG')
        self.influx_token = os.getenv('INFLUX_TOKEN')
        self.influx_url = os.getenv('INFLUX_URL')

        self.sandbox_override = os.getenv('sandbox_override') == 'y'
        self.chrome_proxy = os.getenv('chrome_proxy')
