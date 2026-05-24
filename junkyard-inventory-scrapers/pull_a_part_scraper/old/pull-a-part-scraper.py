from workspace.web_scrapers.junkyard_inventory_scrapers.pull_a_part_scraper.old.utils.inventory_retriever import PullAPartScraper
from datetime import datetime

if __name__ == '__main__':
    paps = PullAPartScraper()
    # paps.scrape(0, datetime.now())
    paps.get_details(0, datetime.now())