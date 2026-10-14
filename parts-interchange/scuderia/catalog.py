from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

BASE_URL = "https://www.scuderiacarparts.com"
DOMAIN = "www.scuderiacarparts.com"
CATALOG_PATH = re.compile(
    r"^/part-finder/([a-z0-9-]+)/([a-z0-9-]+)/oe/(\d+)(?:/(\d+))?(?:/(\d+))?$"
)
SELECTORS = {
    "marque": 'select[aria-label="Select Marque"]',
    "model": 'select[aria-label="Select Model"]',
    "variant": 'select[aria-label="Select Model Variant"]',
    "product_type": 'select[aria-label="Select Product Type"]',
    "category": 'select[aria-label="Select Main OE Parts Main Category"]',
    "diagram": 'select[aria-label="Select Sub Category OE Parts"]',
    "table": "#diagtable",
    "rows": "#diagtable tr.diagrow",
    "part_link": "a.parturl",
    "note": "[data-original-title]",
    "mobile_note": "a.notesurl",
    "stock": ".label-success",
    "enquiry": "a.diagenquirepos",
    "image": ".filter_diagimg img[src]",
    "hotspots": "a.custom-diaghotspot[data-labelcode]",
}


class ScrapeError(Exception):
    """An explicit access, parsing, or persistence failure."""


class Redirected(ScrapeError):
    """The site redirected a request (fetches never follow redirects). A tuning-only model page redirects
    to its /aftermarket/ catalogue (Aston Martin DB11, 2026-10-14), which discovery reads as "no OE"."""


def site_url(value: str, base: str = BASE_URL) -> str:
    url = urljoin(base, value)
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != DOMAIN
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or "%" in parsed.path
        or any(segment in (".", "..") for segment in parsed.path.split("/"))
    ):
        raise ScrapeError(f"invalid_source_url: {value!r}")
    return url


def catalog_url(value: str, base: str = BASE_URL) -> str:
    url = site_url(value, base)
    if not CATALOG_PATH.fullmatch(urlsplit(url).path):
        raise ScrapeError(f"invalid_catalog_url: {url}")
    return url


def text(element: Tag | None) -> str:
    return " ".join(element.stripped_strings) if element else ""


def selected(soup: BeautifulSoup, name: str, url: str) -> tuple[str, str]:
    element = soup.select_one(SELECTORS[name])
    option = element.select_one("option[selected]") if element else None
    if not option or not text(option) or not option.get("value"):
        raise ScrapeError(f"selector_drift: missing selected {name} at {url}")
    return text(option), site_url(str(option["value"]), url)


@dataclass(frozen=True)
class PartRow:
    row_id: str
    part_index: str
    site_part_id: str
    part_number: str
    url: str
    title: str
    notes: str | None
    price_text: str
    quantity_on_diagram: str
    stock_text: str | None
    enquire_only: bool


@dataclass(frozen=True)
class Hotspot:
    part_index: str
    left_percent: float
    top_percent: float
    width_percent: float
    height_percent: float


@dataclass(frozen=True)
class Diagram:
    url: str
    manufacturer: str
    marque: str
    model: str
    model_slug: str
    variant_id: str
    variant_name: str
    variant_url: str
    category: str
    category_url: str
    diagram_id: str
    title: str
    image_url: str
    image_alt: str
    hotspots: list[Hotspot]
    parts: list[PartRow]

    def metadata(self) -> dict:
        return {
            "manufacturer": {
                "name": self.manufacturer,
                "base_url": f"{BASE_URL}/part-finder/{self.marque}",
            },
            "car": {
                "base_url": self.variant_url,
                "car_id": self.variant_id,
                "make": {"name": self.manufacturer, "select_value": self.marque},
                "model": {"name": self.model, "select_value": self.model_slug},
                "year": None,
                "trim": None,
                "engine": None,
            },
            "category": {"name": self.category},
            "subcategory": {"name": self.title},
            "diagram": {
                "base_car_url": self.variant_url,
                "category_url": self.url,
            },
            "image": {"url": self.image_url, "alt_text": self.image_alt},
            "source": {
                "diagram_id": self.diagram_id,
                "variant_name": self.variant_name,
                "category_url": self.category_url,
                "hotspots": [asdict(h) for h in self.hotspots],
            },
        }


@dataclass(frozen=True)
class CatalogPage:
    links: list[str]
    diagram: Diagram | None = None


def parse_rows(soup: BeautifulSoup, url: str) -> list[PartRow]:
    table = soup.select_one(SELECTORS["table"])
    header = table.find("tr") if table else None
    columns = (
        [re.sub(r"\s+", "", text(cell)).lower() for cell in header.find_all(["td", "th"], recursive=False)]
        if header else []
    )
    required = ["partnumber", "partdescription", "price(each)", "qtyondiagram"]
    if any(columns.count(name) != 1 for name in required) or "#" not in columns:
        raise ScrapeError(f"selector_drift: unexpected parts columns at {url}")
    indexes = {name: columns.index(name) for name in required}
    parts = []
    seen_rows = set()
    for row in soup.select(SELECTORS["rows"]):
        cells = row.find_all(["td", "th"], recursive=False)
        if len(cells) != len(columns):
            raise ScrapeError(f"selector_drift: parts row width at {url}")
        number = cells[indexes["partnumber"]].select_one(SELECTORS["part_link"])
        description = cells[indexes["partdescription"]].select_one(SELECTORS["part_link"])
        if not number or not description:
            raise ScrapeError(f"schema_mismatch: missing part links at {url}")
        part_url = site_url(str(number.get("href", "")), url)
        match = re.fullmatch(r"/part/(\d+)/[a-z0-9-]+/[^/]+/[^/]+\.html", urlsplit(part_url).path)
        row_id = str(row.get("data-divid", ""))
        label = str(row.get("data-labelcode", ""))
        quantity = text(cells[indexes["qtyondiagram"]])
        if not match or not row_id or row_id in seen_rows or not label or not text(number) or not text(description) or not quantity:
            raise ScrapeError(f"schema_mismatch: invalid part identity/quantity at {url}")
        seen_rows.add(row_id)
        note = cells[indexes["partdescription"]].select_one(SELECTORS["note"])
        notes = str(note.get("data-original-title", "")).strip() if note else ""
        if not notes:
            notes = text(row.select_one(SELECTORS["mobile_note"]))
        parts.append(PartRow(
            row_id=row_id, part_index=label, site_part_id=match[1],
            part_number=text(number), url=part_url, title=text(description),
            notes=notes or None, price_text=text(cells[indexes["price(each)"]]),
            quantity_on_diagram=quantity,
            stock_text=text(cells[indexes["partdescription"]].select_one(SELECTORS["stock"])) or None,
            enquire_only=row.select_one(SELECTORS["enquiry"]) is not None,
        ))
    if not parts:
        raise ScrapeError(f"selector_drift: empty parts table at {url}")
    return parts


def parse_hotspots(soup: BeautifulSoup, url: str) -> list[Hotspot]:
    elements = soup.select(SELECTORS["hotspots"])
    if not elements:
        raise ScrapeError(f"selector_drift: missing diagram hotspots at {url}")
    # The first group belongs to the enlargement; other views repeat its callouts.
    container = elements[0].parent
    hotspots = []
    for element in container.select(SELECTORS["hotspots"]):
        styles = dict(re.findall(r"(left|top|width|height)\s*:\s*([\d.]+)%", str(element.get("style", ""))))
        label = str(element.get("data-labelcode", ""))
        if len(styles) != 4 or not label:
            raise ScrapeError(f"schema_mismatch: invalid hotspot geometry at {url}")
        values = {key: float(value) for key, value in styles.items()}
        if any(not 0 <= value <= 100 for value in values.values()):
            raise ScrapeError(f"schema_mismatch: hotspot outside image at {url}")
        hotspots.append(Hotspot(label, values["left"], values["top"], values["width"], values["height"]))
    return hotspots


def parse_catalog(html: str, url: str) -> CatalogPage:
    url = catalog_url(url)
    match = CATALOG_PATH.fullmatch(urlsplit(url).path)
    if match is None:
        raise ScrapeError(f"invalid_catalog_url: {url}")
    soup = BeautifulSoup(html, "html.parser")
    if soup.title and "Just a moment" in text(soup.title):
        raise ScrapeError(f"access_blocked: challenge HTML at {url}")
    manufacturer, marque_url = selected(soup, "marque", url)
    model, model_url = selected(soup, "model", url)
    variant_name, variant_url = selected(soup, "variant", url)
    expected_variant = f"{BASE_URL}/part-finder/{match[1]}/{match[2]}/oe/{match[3]}"
    if (
        variant_url != expected_variant
        or marque_url != f"{BASE_URL}/part-finder/{match[1]}"
        or model_url != f"{BASE_URL}/part-finder/{match[1]}/{match[2]}"
    ):
        raise ScrapeError(f"schema_mismatch: wrong selected vehicle at {url}")
    if not match[5]:
        selector = SELECTORS["diagram" if match[4] else "category"]
        links = []
        for option in soup.select(f"{selector} option[value]"):
            if not option["value"]:
                continue
            child = catalog_url(str(option["value"]), url)
            if not child.startswith(url + "/") or child.count("/") != url.count("/") + 1:
                raise ScrapeError(f"schema_mismatch: unexpected child {child} at {url}")
            if child not in links:
                links.append(child)
        if not links:
            raise ScrapeError(f"selector_drift: empty catalog level at {url}")
        return CatalogPage(links)
    category, category_url = selected(soup, "category", url)
    title, diagram_url = selected(soup, "diagram", url)
    if diagram_url != url or category_url != url.rsplit("/", 1)[0]:
        raise ScrapeError(f"schema_mismatch: wrong selected diagram/category at {url}")
    image = soup.select_one(SELECTORS["image"])
    if not image:
        raise ScrapeError(f"selector_drift: missing main diagram image at {url}")
    image_url = site_url(str(image["src"]), url)
    if not urlsplit(image_url).path.startswith(f"/images/diagrams/{match[1]}/"):
        raise ScrapeError(f"schema_mismatch: wrong diagram image at {url}")
    return CatalogPage([], Diagram(
        url=url, manufacturer=manufacturer, marque=match[1],
        model=model.removeprefix(manufacturer + " "), model_slug=match[2],
        variant_id=match[3], variant_name=variant_name, variant_url=variant_url,
        category=category, category_url=category_url, diagram_id=match[5],
        title=title, image_url=image_url, image_alt=str(image.get("alt", "")),
        hotspots=parse_hotspots(soup, url), parts=parse_rows(soup, url),
    ))


# ── part-finder listing levels (discovery, docs/design.md §3) ───────────────────────────────────

@dataclass(frozen=True)
class Option:
    name: str
    url: str

    @property
    def slug(self) -> str:
        return self.url.rstrip("/").rsplit("/", 1)[-1]


def _listing(html: str, url: str) -> BeautifulSoup:
    soup = BeautifulSoup(html, "html.parser")
    if soup.title and "Just a moment" in text(soup.title):
        raise ScrapeError(f"access_blocked: challenge HTML at {url}")
    return soup


def _options(soup: BeautifulSoup, name: str, url: str, parent: str) -> list[Option]:
    """The select's real options, each a direct child of `parent` on the site (placeholders skipped)."""
    out = []
    for option in soup.select(f"{SELECTORS[name]} option[value]"):
        value = str(option["value"])
        if not value:
            continue
        child = site_url(value, url)
        if not child.startswith(parent + "/") or "/" in child[len(parent) + 1:]:
            continue  # e.g. a tuning-catalogue variant under /aftermarket/
        if child not in (o.url for o in out):
            out.append(Option(text(option), child))
    return out


def parse_marques(html: str, url: str) -> list[Option]:
    """Every marque in the part-finder (any part-finder page carries the full list)."""
    soup = _listing(html, url)
    if not soup.select_one(SELECTORS["marque"]):
        raise ScrapeError(f"selector_drift: missing marque list at {url}")
    marques = _options(soup, "marque", url, BASE_URL + "/part-finder")
    if not marques:
        raise ScrapeError(f"selector_drift: empty marque list at {url}")
    return marques


def parse_models(html: str, url: str) -> list[Option]:
    """A marque's models. Marques without models serve a page without the part-finder at all (Alpine,
    Pagani, Mercedes, 2026-10-14), so no model list means an empty marque. Layout drift is caught at the
    start page, which must carry the marque list (parse_marques)."""
    return _options(_listing(html, url), "model", url, url)


def parse_oe_link(html: str, url: str) -> str | None:
    """The model's OE catalogue (`Original Parts` product type), or None for tuning-only models. Some
    tuning-only model pages have no product type list at all (Alfa Romeo 4C, BMW 1M, 2026-10-14); a
    marque losing all its OE models would show in discovery's per-marque counts, not here."""
    soup = _listing(html, url)
    oe = [o for o in _options(soup, "product_type", url, url) if o.slug == "oe"]
    return oe[0].url if oe else None


def parse_variants(html: str, url: str) -> list[Option]:
    """An OE catalogue's model variants. A single-variant model shows the list disabled with its one
    variant pre-selected (Rolls-Royce Cullinan); it is listed the same way."""
    soup = _listing(html, url)
    variants = [o for o in _options(soup, "variant", url, url) if CATALOG_PATH.fullmatch(urlsplit(o.url).path)]
    if not variants:
        raise ScrapeError(f"selector_drift: no OE variants at {url}")
    return variants
