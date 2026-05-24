import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from .config import Config


class BrowserUtil:

    browser: webdriver

    def __init__(self, cfg: Config):
        """
        BrowserUtil, creates a headless browser using selenium webdriver. Sandbox can be turned off if absolutely necessary and a proxy address can be provided as well

        :param debug_port: str, string port number
        :param sandbox: boolean = True, turns off sandbox if set to false
        :param proxy: str = None, will set proxy server for chrome if provided
        """
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        if cfg.sandbox_override:
            options.add_argument('--no-sandbox')
        if cfg.chrome_proxy:
            options.add_argument(f'--proxy-server={cfg.chrome_proxy}')
        options.add_argument("--remote-debugging-port=" + cfg.DEBUG_PORT)

        self.browser = webdriver.Chrome(ChromeDriverManager().install(), options=options)
        self.browser.implicitly_wait(10)

    def navigate(self, location: str):
        """
        Navigates to the provided location

        :param location: str, url
        """
        self.browser.get(location)

    def get_page_source(self):
        """
        Returns the raw page text for the current browser page
        """
        return self.browser.page_source

    def get_browser(self):
        """
        Returns browser instance
        """
        return self.browser
