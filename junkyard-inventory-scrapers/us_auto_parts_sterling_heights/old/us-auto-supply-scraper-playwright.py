from playwright.sync_api import sync_playwright, Page, Locator
from workspace.web_scrapers.junkyard_inventory_scrapers.us_auto_parts_sterling_heights.old.config import Config
import re
import math
import json


class UsAutoSupplyScraper:

    def __init__(self, config):
        self.config = config

    def get_next_button(self, page: Page) -> Locator:
        return page.locator('xpath=//li[@id="vehicles_next"] | //li[@id="vehiclesw_next"]')

    def get_total_entries(self, page: Page) -> int:
        try:
            info_panel = page.locator('xpath=//div[@id="vehicles_info"] | //div[@id="vehiclesw_info"]')
            text = info_panel.inner_text()
            rgx = r'[a-zA-Z]+ ([0-1]+) to ([0-9]+) of ([0-9,]+) [a-zA-Z]+'
            results = re.findall(rgx, text)
            total = int(results[0][2].replace(',', ''))
            return total
        except Exception as ex:
            print(ex)
            return 0

    def parse_table(self, page: Page) -> list:
        table = page.locator('xpath=//table[@id="vehicles"] | //table[@id="vehiclesw"]')
        rows = table.locator('tr').all()
        cars = []
        for row in rows:
            car = {}
            cells = row.locator('td').all()
            if len(cells) == 0:
                continue
            for cell in cells:
                value = cell.inner_text()
                key = cell.get_attribute('data-label')
                car[key] = value
            cars.append(car)
        return cars

    def start(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()

            page.goto(self.config['url'])
            page.wait_for_timeout(2000)

            page.wait_for_selector('xpath=//select[@name="vehicles_length"] | //select[@name="vehiclesw_length"]')
            page.select_option(
                'xpath=//select[@name="vehicles_length"] | //select[@name="vehiclesw_length"]',
                label='100'
            )

            page.wait_for_timeout(2000)

            total = self.get_total_entries(page)
            pages = math.ceil(total / 100)
            cars = []

            for _ in range(pages):
                cars.extend(self.parse_table(page))
                self.get_next_button(page).click()
                page.wait_for_timeout(2000)

            if len(cars) != total:
                print(f'total was {len(cars)} but expected {total}')

            with open('cars_output.json', 'w') as f:
                f.write(json.dumps(cars, indent=2))


if __name__ == '__main__':
    cfg = Config.get('us-auto-supply-sterling-heights')
    scraper = UsAutoSupplyScraper(cfg)
    scraper.start()
