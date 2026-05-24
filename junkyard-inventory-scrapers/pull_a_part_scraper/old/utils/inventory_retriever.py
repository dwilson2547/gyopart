import requests
import json
from workspace.web_scrapers.junkyard_inventory_scrapers.pull_a_part_scraper.old.utils.urls import ScrapeUrls
from datetime import datetime
from workspace.web_scrapers.junkyard_inventory_scrapers.pull_a_part_scraper.old.utils.config import Config
from workspace.web_scrapers.junkyard_inventory_scrapers.pull_a_part_scraper.old.utils.proxy_utils import ProxyUtils
from typing import List
import time
from sqlalchemy.orm import Session
from workspace.web_scrapers.junkyard_inventory_scrapers.pull_a_part_scraper.old.utils.save_util import SaveUtil

class PullAPartScraper():

    url_util = ScrapeUrls()
    proxy_utils = ProxyUtils('http://localhost:8118')
    headers = {
        'Content-Type': 'application/json'
    }
    session: Session
    save_util: SaveUtil

    def __init__(self):
        self.save_util = SaveUtil('/home/daniel/documents/selenium_test_project/yard_inventory_scraper/pull_a_part_scraper/test_save')

    def get_through_proxy(self, url: str):
        return requests.get(url, headers=self.headers, proxies=self.proxy_utils.get_proxies())
    
    def post_through_proxy(self, url: str, payload: dict):
        return requests.post(url, json=payload, proxies=self.proxy_utils.get_proxies())

    def inventory_delay(self):
        time.sleep(Config.inventory_delay)
    
    def detail_delay(self):
        time.sleep(Config.detail_delay)

    def retrieve_locations(self):
        return self.get_through_proxy(self.url_util.get_locations_url())
    
    def retrieve_makes(self):
        return self.get_through_proxy(self.url_util.get_makes_url())

    def get_car_inventory(self, locations_list: List[int], make_list: List[int]):
        inventory = {}
        for location in locations_list:
            inventory[location] = {}
            for make in make_list:
                inventory_resp = self.post_through_proxy(self.url_util.get_inventory_url(),
                                                        self.url_util.build_inventory_request_payload([location], make))
                inventory[location][make] = inventory_resp.json()
                time.sleep(Config.inventory_delay)
        return inventory
    
    def get_car_details(self, location_id: int, ticket_id: int, line_id: int):
        return self.get_through_proxy(self.url_util.get_vehicle_details_url(loc_id=location_id, ticket_id=ticket_id, line_id=line_id))

    def scrape(self, run_id: int, start_time: datetime):
        locations_resp = self.retrieve_locations()
        locations = locations_resp.json()
        location_ids = [loc['locationID'] for loc in locations]
        self.inventory_delay()
        makes_resp = self.retrieve_makes()
        makes = makes_resp.json()
        make_ids = [make['makeID'] for make in makes]
        self.inventory_delay()

        inventory = self.get_car_inventory(locations_list=location_ids, make_list=make_ids)

        for location, location_inventory in inventory.items():
            for make, location_make_inventory in location_inventory.items():
                for car in location_make_inventory['exact']:
                    details_resp = self.get_car_details(location, car['ticketID'], car['lineID'])
                    details = details_resp.json()
                    car.update(details)
                    self.detail_delay()

        self.save_util.save_inventory(inventory=inventory, run_id=run_id, start_time=start_time)
        
        return inventory
    

    def get_details(self, run_id: int, start_time: datetime):
        inventory = {}
        with open('/home/daniel/documents/selenium_test_project/yard_inventory_scraper/pull_a_part_scraper/test_save/partial_save.json', 'r') as f:
            inventory = json.load(f)

        for location, location_inventory in inventory.items():
            for make, location_make_inventory in location_inventory.items():
                if type(location_make_inventory) == list:
                    for car in location_make_inventory[0]['exact']:
                        if 'trim' in car:
                            continue
                        try:
                            details_resp = self.get_car_details(location, car['ticketID'], car['lineID'])
                            if details_resp.status_code != 200:
                                print('error with request')
                            details = details_resp.json()
                        except Exception as ex:
                            print(ex)
                            self.save_util.save_inventory(inventory=inventory, run_id=run_id, start_time=datetime.now())
                        car.update(details)
                        self.detail_delay()

        self.save_util.save_inventory(inventory=inventory, run_id=run_id, start_time=start_time)
        
