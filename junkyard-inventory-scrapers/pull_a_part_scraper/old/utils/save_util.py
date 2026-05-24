from datetime import datetime
import os
from workspace.web_scrapers.junkyard_inventory_scrapers.pull_a_part_scraper.old.exceptions import SaveDirNotProvidedException
from workspace.web_scrapers.junkyard_inventory_scrapers.pull_a_part_scraper.old.utils.config import Config
import bz2
import json

class SaveUtil():

    save_dir = ""
    _time_format = '%Y_%m_%d_t_%H_%M_%S'

    def __init__(self, inventory_save_dir: str):
        env_save_dir = os.getenv('inventory_save_dir')
        if not inventory_save_dir or env_save_dir:
            raise SaveDirNotProvidedException('Save dir not provided, missing "inventory_save_dir" environment variable, shutting down')
        self.save_dir = env_save_dir if env_save_dir else inventory_save_dir

    def save_inventory(self, inventory: dict, run_id: int, start_time: datetime):
        save_path = os.path.join(self.save_dir, Config.yard_name, str(run_id) + '_' + start_time.strftime(self._time_format) + '.bz2')
        with bz2.open(save_path, 'wt') as f:
            f.write(json.dumps(inventory))