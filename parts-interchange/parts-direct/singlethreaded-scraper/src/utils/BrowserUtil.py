import os

from selenium import webdriver

CHROME_PROXY = os.getenv('chrome_proxy')
REMOTE_EXECUTOR = os.getenv('remote_executor')

class BrowserUtil:

    browser: webdriver.Remote

    def __init__(self, debug_port: str, sandbox=True, proxy=None):
        """
        BrowserUtil, creates a headless browser using selenium webdriver. Sandbox can be turned off if absolutely necessary and a proxy address can be provided as well

        :param debug_port: str, string port number
        :param sandbox: boolean = True, turns off sandbox if set to false
        :param proxy: str = None, will set proxy server for chrome if provided
        """
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument(f'--proxy-server={CHROME_PROXY}')
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-gpu')
        self.browser = webdriver.Remote(
            command_executor=REMOTE_EXECUTOR,
            options=chrome_options
        )

        self.browser.set_page_load_timeout(30)
        self.browser.implicitly_wait(30)

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
    
    def close(self):
        """
        Closes browser instance
        """
        self.browser.close()