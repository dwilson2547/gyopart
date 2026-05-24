from utils.BrowserUtil import BrowserUtil
from bs4 import BeautifulSoup as bs
from workspace.web_scrapers.junkyard_inventory_scrapers.us_auto_parts_sterling_heights.old.config import Config
from selenium import webdriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
import time
import re
import math
import json

class UsAutoSupplyScraper:

    def __init__(self, config):
        self.config = config

    def get_next_button(self, browser: webdriver) -> WebElement:
        return browser.find_element(By.XPATH, '//li[@id="vehicles_next"] | //li[@id="vehiclesw_next"]')
    
    def get_total_entries(self, browser: webdriver):
        try:
            info_panel: WebElement = browser.find_element(By.XPATH, '//div[@id="vehicles_info"] | //div[@id="vehiclesw_info"]')
            rgx = '[a-zA-Z]+ ([0-1]+) to ([0-9]+) of ([0-9,]+) [a-zA-Z]+'
            results = re.findall(rgx, info_panel.text)
            
            total = int(results[0][2].replace(',', ''))

            return total
        except Exception as ex:
            print(ex)
            return 0
        
    def parse_table(self, browser: webdriver):
        table: WebElement = browser.find_element(By.XPATH, '//table[@id="vehicles"] | //table[@id="vehiclesw"]')
        rows = table.find_elements(By.TAG_NAME, 'tr')
        cars = []
        for row in rows:
            car = {}
            cells = row.find_elements(By.TAG_NAME, 'td')
            if len(cells) == 0:
                continue
            for cell in cells:
                value = cell.text
                key = cell.get_attribute('data-label')
                car[key]=value
            cars.append(car)
        return cars

    def start(self):
        browser_util = BrowserUtil('9222')
        browser_util.navigate(self.config['url'])
        
        time.sleep(2)

        ddl = WebDriverWait(browser_util.get_browser(), 10).until(
            EC.presence_of_element_located((By.XPATH, '//select[@name="vehicles_length"] | //select[@name="vehiclesw_length"]'))
        )
        slct = Select(ddl)
        slct.select_by_visible_text('100')

        time.sleep(2)

        total = self.get_total_entries(browser_util.get_browser())

        pages = math.ceil(total/100)
        cars = []
        
        for _ in range(pages):
            cars.extend(self.parse_table(browser_util.get_browser()))
            button = self.get_next_button(browser_util.get_browser())
            button.click()
            time.sleep(2)

        if len(cars) != total:
            print(f'total was {len(cars)} but expected {total}')

        with open('cars_output.json', 'w') as f:
            f.write(json.dumps(cars, indent=2))



        # with open('source.html', 'w') as f:
        #     f.write(page_source)

        # with open('source.html') as f:
        #     page_source = f.read()

        # soup = bs(page_source, 'html.parser')

        # table = soup.find('table', {'id': 'vehicles'})
        # rows = table.findChildren(['th', 'tr'])
        # for row in rows:
        #     cells = row.findChildren('td')
        #     for cell in cells:
        #         value = cell.string

if __name__ == '__main__':
    cfg = Config.get('us-auto-supply-sterling-heights')
    scraper = UsAutoSupplyScraper(cfg)
    scraper.start()