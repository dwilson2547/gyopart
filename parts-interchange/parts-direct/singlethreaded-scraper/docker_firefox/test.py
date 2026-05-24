from selenium import webdriver

chrome_options = webdriver.ChromeOptions()
chrome_options.add_argument('--proxy-server=http://192.168.0.20:8118')
chrome_options.add_argument('--headless')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-gpu')
driver = webdriver.Remote(
    command_executor='http://localhost:3000/webdriver',
    options=chrome_options
)
driver.get("https://www.whatismyip.com/")
driver.quit()