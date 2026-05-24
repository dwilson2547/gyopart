import os
from workspace.web_scrapers.junkyard_inventory_scrapers.pull_a_part_scraper.old.exceptions import ProxyNotProvidedException

class ProxyUtils:

    proxies: dict

    def __init__(self, proxy_string: str = None):
        env_proxy = os.getenv('chrome_proxy')
        if not proxy_string and not env_proxy:
            raise ProxyNotProvidedException('No proxy provided, missing "chrome_proxy" environment variable, shutting down')
        prx = env_proxy if env_proxy else proxy_string
        self.proxies = {
                'http': prx,
                'https': prx
            }

    def get_proxies(self):
        return self.proxies