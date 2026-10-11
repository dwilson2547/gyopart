from __future__ import annotations

import copy
import json
import time
from datetime import datetime
from typing import TYPE_CHECKING
from urllib.parse import urlparse, urlencode

import requests

from bootstrap import ensure_singlethreaded_src_path

ensure_singlethreaded_src_path()

from request_auth_client import RequestAuthClient
from utils import format_print_msg
from utils.Constants import Steps, keys
from utils.Exceptions import TreeBuilderError

if TYPE_CHECKING:
    from playwright.sync_api import Page


class RecentTreeBuilder:
    def __init__(
        self,
        base_url: str,
        years_to_refresh: int,
        request_auth: RequestAuthClient,
        current_year: int = None,
        csrf_token: str = None,
    ):
        self.base_url = base_url
        self.ALL_MAKES_URL = f"{self.base_url}/ajax/vehicle-picker/makes/all"
        self.PICKER_AJAX_URL = f"{self.base_url}/ajax/vehicle-picker/next"
        self.domain = urlparse(base_url).netloc
        self.request_auth = request_auth
        self.years_to_refresh = years_to_refresh
        self.current_year = current_year or datetime.utcnow().year
        self.minimum_year = self.current_year - self.years_to_refresh + 1
        self.csrf_token = csrf_token

    def scrape_car_list(self, page: "Page | None" = None):
        """Build the vehicle tree. When page is provided, AJAX calls run inside the
        browser so they share the Cloudflare cookie jar and TLS fingerprint."""
        session = None if page else requests.Session()
        tree = {}

        if page:
            with self.request_auth.acquire(self.domain) as permit:
                result = page.evaluate(
                    """async (url) => {
                        const r = await fetch(url, {
                            credentials: 'include',
                            headers: {'X-Requested-With': 'XMLHttpRequest'},
                        });
                        return {status: r.status, body: await r.text()};
                    }""",
                    self.ALL_MAKES_URL,
                )
                permit.set_status(result["status"])
            if result["status"] != 200:
                raise TreeBuilderError(f"Failed to fetch makes: HTTP {result['status']}")
            makes = json.loads(result["body"])
        else:
            with self.request_auth.acquire(self.domain) as permit:
                resp = session.get(self.ALL_MAKES_URL)
                permit.set_status(resp.status_code)
            makes = resp.json()

        for make in makes:
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

                    models = self._fetch_options(self._build_params(Steps.MODEL, year, make["url"]), session, page)
                    for model in models:
                        format_print_msg(model["ui"], 2)
                        model[keys.TRIMS] = {}
                        make[keys.MODELS][model["url"]] = model

                        trims = self._fetch_options(self._build_params(Steps.TRIM, year, make["url"], model["url"]), session, page)
                        for trim in trims:
                            format_print_msg(trim["ui"], 3)
                            trim[keys.ENGINES] = {}
                            model[keys.TRIMS][trim["url"]] = trim

                            engines = self._fetch_options(
                                self._build_params(Steps.ENGINE, year, make["url"], model["url"], trim["url"]),
                                session, page,
                            )
                            for engine in engines:
                                format_print_msg(engine["ui"], 4)
                                engine[keys.CATEGORIES] = {}
                                engine[keys.PAGE_URL] = self._build_car_url(
                                    year, make["url"], model["url"], trim["url"], engine["url"]
                                )
                                trim[keys.ENGINES][engine["url"]] = engine
        except Exception as ex:
            raise TreeBuilderError(ex)

        return tree

    def _fetch_options(self, params: dict, session: requests.Session = None, page: "Page | None" = None, retries: int = 0) -> list:
        """GET /ajax/vehicle-picker/next with params as query string.
        The endpoint is GET-only and requires X-CSRF-TOKEN from the page meta tag."""
        should_retry = False
        result_data = None

        with self.request_auth.acquire(self.domain) as permit:
            try:
                if page:
                    result = page.evaluate(
                        """async ([url, params, csrf]) => {
                            const qs = new URLSearchParams(params);
                            const headers = {'X-Requested-With': 'XMLHttpRequest'};
                            if (csrf) headers['X-CSRF-TOKEN'] = csrf;
                            const r = await fetch(`${url}?${qs}`, {
                                method: 'GET',
                                credentials: 'include',
                                headers,
                            });
                            const body = await r.text();
                            return {status: r.status, body};
                        }""",
                        [self.PICKER_AJAX_URL, params, self.csrf_token],
                    )
                    permit.set_status(result["status"])
                    if result["status"] != 200:
                        print(f"[picker] GET {self.PICKER_AJAX_URL} → {result['status']}: {result['body'][:400]}")
                        raise Exception(f"HTTP {result['status']}")
                    result_data = json.loads(result["body"])
                else:
                    url = self.PICKER_AJAX_URL + "?" + urlencode(params)
                    headers = {"X-Requested-With": "XMLHttpRequest"}
                    if self.csrf_token:
                        headers["X-CSRF-TOKEN"] = self.csrf_token
                    resp = session.get(url, headers=headers)
                    permit.set_status(resp.status_code)
                    result_data = resp.json()
            except Exception as ex:
                permit.set_status(0)
                if retries > 3:
                    raise ex
                should_retry = True

        if should_retry:
            print("Retrying picker request...")
            time.sleep(5)
            return self._fetch_options(params, session=session, page=page, retries=retries + 1)

        return result_data

    def _build_params(self, step: str, year: str, make: str = None, model: str = None, trim: str = None) -> dict:
        params = {
            "type": "get_next_json",
            "step": step,
            "picker_type": "normal",
            "selected[year]": year,
        }
        if make:
            params["selected[make]"] = make
        if model:
            params["selected[model]"] = model
        if trim:
            params["selected[trim]"] = trim
        return params

    def _build_car_url(self, year, make, model, trim, engine) -> str:
        return self.base_url + f"/v-{year}-{make}-{model}--{trim}--{engine}"
