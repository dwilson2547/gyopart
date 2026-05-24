import copy
import os
import time

from requests_html import HTMLSession
from urllib3 import encode_multipart_formdata
from utils import format_print_msg
from .constants import Steps, CommonKeys
from .exceptions import TreeBuilderError

CHROME_PROXY = os.getenv('chrome_proxy')

class TreeBuilder:

    base_url: str

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.ALL_MAKES_URL = f'{self.base_url}/ajax/vehicle-picker/makes/all'
        self.PICKER_AJAX_URL = f'{self.base_url}/ajax/vehicle-picker/next'
        if CHROME_PROXY:
            self.proxies = {
                'http': CHROME_PROXY,
                'https': CHROME_PROXY
            }
        else:
            self.proxies = None

    def scrape_car_list(self):
        
        session = HTMLSession()

        tree = {}
        resp = session.get(self.ALL_MAKES_URL, proxies=self.proxies).json()

        for make in resp:
            # For some reason they give us makes with start and end years
            # even though the picker works in the opposite direction...
            # So we have to build the year list and start the tree there 
            # and add the make to each year record in the tree
            year_range = list(range(make['start_year'], make['end_year'] + 1))
            for year in year_range:
                if str(year) not in tree:
                    tree[str(year)] = {
                        'makes': {}
                    }
                if make['url'] not in tree[str(year)][CommonKeys.MAKES]:
                    make[CommonKeys.MODELS] = {}
                    tree[str(year)][CommonKeys.MAKES][make['url']] = copy.deepcopy(make)
        
        # Now we can continue on to getting the other options, starting with models
        try:
            for year in tree:
                format_print_msg(year)
                for m in tree[year][CommonKeys.MAKES]:
                    make = tree[year][CommonKeys.MAKES][m]
                    format_print_msg(make['ui'], 1)

                    model_form = self._build_form(Steps.MODEL, year, make['url'])
                    body, header = encode_multipart_formdata(fields=model_form)
                    models = self.post(body, header, session)
                    for model in models:
                        format_print_msg(model['ui'], 2)
                        model[CommonKeys.TRIMS] = {}
                        make[CommonKeys.MODELS][model['url']] = model

                        # Then trims
                        trim_form = self._build_form(Steps.TRIM, year, make['url'], model['url'])
                        trim_body, trim_header = encode_multipart_formdata(fields=trim_form)
                        trims = self.post(trim_body, trim_header, session)
                        for trim in trims:
                            format_print_msg(trim['ui'], 3)
                            trim[CommonKeys.ENGINES] = {}
                            model[CommonKeys.TRIMS][trim['url']] = trim

                            # And finally engines
                            engine_form = self._build_form(Steps.ENGINE, year, make['url'], model['url'], trim['url'])
                            engine_body, engine_header = encode_multipart_formdata(fields=engine_form)
                            engines = self.post(engine_body, engine_header, session)
                            for engine in engines:
                                format_print_msg(engine['ui'], 4)
                                engine[CommonKeys.CATEGORIES] = {}
                                # Build the url for the categories page
                                engine[CommonKeys.PAGE_URL] = self.build_car_url(year, make['url'], model['url'], trim['url'], engine['url'])
                                trim[CommonKeys.ENGINES][engine['url']] = engine
        except Exception as ex:
            print(ex)
            raise TreeBuilderError(ex)
        
        return tree

    def build_car_url(self, year, make, model, trim, engine):
        """
        Formats provided year, make, model, trim, and entine into url
        """
        return self.base_url + f'/v-{year}-{make}-{model}--{trim}--{engine}'
    
    def post(self, body, content_type_header, session: HTMLSession, retries=0):
        """
        Sends post request
        """
        try:
            return session.post(url=self.PICKER_AJAX_URL, data=body, headers={'Content-Type': content_type_header}, proxies=self.proxies).json()
        except Exception as ex:
            if retries > 3:
                raise ex
            else:
                print('Retrying post request...')
                time.sleep(5)
                return self.post(body, content_type_header, session, retries + 1)

    def _build_form(self, step: str, year: str, make: str = None, model: str = None, trim: str = None):
        """
        Builds reqeust form for next level of data, also waits 3.5 seconds
        """
        time.sleep(3.5)
        form = {
            "type": "get_next_json",
            "step": step,
            "picker_type": "normal",
            "selected[year]": year
        }
        if make:
            form["selected[make]"] = make
        if model:
            form["selected[model]"] = model
        if trim:
            form["selected[trim]"] = trim
        return form