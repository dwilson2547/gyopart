import copy
import time
from datetime import datetime

import requests
from urllib3 import encode_multipart_formdata

from bootstrap import ensure_singlethreaded_src_path

ensure_singlethreaded_src_path()

from utils import format_print_msg
from utils.Constants import Steps, keys
from utils.Exceptions import TreeBuilderError


class RecentTreeBuilder:
    def __init__(self, base_url: str, years_to_refresh: int, current_year: int = None):
        self.base_url = base_url
        self.ALL_MAKES_URL = f"{self.base_url}/ajax/vehicle-picker/makes/all"
        self.PICKER_AJAX_URL = f"{self.base_url}/ajax/vehicle-picker/next"
        self.proxies = None
        self.years_to_refresh = years_to_refresh
        self.current_year = current_year or datetime.utcnow().year
        self.minimum_year = self.current_year - self.years_to_refresh + 1

    def scrape_car_list(self):
        session = self._create_session()
        tree = {}
        resp = session.get(self.ALL_MAKES_URL, proxies=self.proxies).json()

        for make in resp:
            start_year = max(make["start_year"], self.minimum_year)
            end_year = min(make["end_year"], self.current_year)
            if start_year > end_year:
                continue

            for year in range(start_year, end_year + 1):
                year_key = str(year)
                if year_key not in tree:
                    tree[year_key] = {keys.MAKES: {}}
                if make["url"] not in tree[year_key][keys.MAKES]:
                    make[keys.MODELS] = {}
                    tree[year_key][keys.MAKES][make["url"]] = copy.deepcopy(make)

        try:
            for year in tree:
                format_print_msg(year)
                for make_key in tree[year][keys.MAKES]:
                    make = tree[year][keys.MAKES][make_key]
                    format_print_msg(make["ui"], 1)

                    model_form = self._build_form(Steps.MODEL, year, make["url"])
                    body, header = self._encode_form(model_form)
                    models = self.post(body, header, session)
                    for model in models:
                        format_print_msg(model["ui"], 2)
                        model[keys.TRIMS] = {}
                        make[keys.MODELS][model["url"]] = model

                        trim_form = self._build_form(Steps.TRIM, year, make["url"], model["url"])
                        trim_body, trim_header = self._encode_form(trim_form)
                        trims = self.post(trim_body, trim_header, session)
                        for trim in trims:
                            format_print_msg(trim["ui"], 3)
                            trim[keys.ENGINES] = {}
                            model[keys.TRIMS][trim["url"]] = trim

                            engine_form = self._build_form(Steps.ENGINE, year, make["url"], model["url"], trim["url"])
                            engine_body, engine_header = self._encode_form(engine_form)
                            engines = self.post(engine_body, engine_header, session)
                            for engine in engines:
                                format_print_msg(engine["ui"], 4)
                                engine[keys.CATEGORIES] = {}
                                engine[keys.PAGE_URL] = self.build_car_url(
                                    year, make["url"], model["url"], trim["url"], engine["url"]
                                )
                                trim[keys.ENGINES][engine["url"]] = engine
        except Exception as ex:
            raise TreeBuilderError(ex)

        return tree

    def _create_session(self):
        return requests.Session()

    def _encode_form(self, model_form):
        return encode_multipart_formdata(fields=model_form)

    def build_car_url(self, year, make, model, trim, engine):
        return self.base_url + f"/v-{year}-{make}-{model}--{trim}--{engine}"

    def post(self, body, content_type_header, session, retries=0):
        try:
            return session.post(
                url=self.PICKER_AJAX_URL,
                data=body,
                headers={"Content-Type": content_type_header},
                proxies=self.proxies,
            ).json()
        except Exception as ex:
            if retries > 3:
                raise ex
            print("Retrying post request...")
            time.sleep(5)
            return self.post(body, content_type_header, session, retries + 1)

    def _build_form(self, step: str, year: str, make: str = None, model: str = None, trim: str = None):
        time.sleep(3.5)
        form = {
            "type": "get_next_json",
            "step": step,
            "picker_type": "normal",
            "selected[year]": year,
        }
        if make:
            form["selected[make]"] = make
        if model:
            form["selected[model]"] = model
        if trim:
            form["selected[trim]"] = trim
        return form
