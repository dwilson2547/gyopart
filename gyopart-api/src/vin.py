"""
NHTSA VIN decode for the garage, and narrowing the decode to catalogue cars.

The narrowing mirrors junkyard-platform `pipeline/car_matcher.py` (the yard VIN resolver): year + make + loose
model name, then engine displacement/cylinders, fuel, trim — each filter only when it keeps at least one car.
Kept as a copy rather than a shared package because it is ~60 lines and the two services read the catalogue
through different layers (Core tables there, ORM here).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import httpx

NHTSA_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVINValues/{vin}"
VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")

_ENGINE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)L\s+[A-Z]+(\d+)\s*-\s*(.+?)\s*$", re.IGNORECASE)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


@dataclass
class EngineSpec:
    displacement_l: float | None = None
    cylinders: int | None = None
    fuel: str | None = None


@dataclass
class CatalogueRow:
    car_id: int
    model: str
    trim: str | None
    engine: str | None


@dataclass
class Narrowed:
    rows: list[CatalogueRow]
    narrowed_by: list[str] = field(default_factory=list)


def decode(vin: str, timeout: float = 10.0) -> dict:
    """The NHTSA DecodeVINValues result row for one VIN. Raises httpx.HTTPError when NHTSA is unreachable."""
    resp = httpx.get(NHTSA_URL.format(vin=vin), params={"format": "json"}, timeout=timeout)
    resp.raise_for_status()
    results = resp.json().get("Results") or []
    if not results:
        raise httpx.HTTPError("NHTSA returned no result row")
    return results[0]


def name_key(name: str | None) -> str:
    """Loose name key: 'Town and Country' == 'Town & Country', 'F-150' == 'F150'."""
    return _NON_ALNUM.sub("", (name or "").lower().replace("&", "and"))


def model_keys(raw: dict) -> set[str]:
    """Catalogue model names the decode may mean ('Caravan/Grand Caravan'; Ram 'Ram' + Series '1500')."""
    model = (raw.get("Model") or "").strip()
    series = (raw.get("Series") or "").strip()
    names = {model, *model.split("/")}
    if series:
        names |= {f"{n} {series}" for n in list(names)}
    return {name_key(n) for n in names if n.strip()}


def parse_catalogue_engine(name: str | None) -> EngineSpec:
    m = _ENGINE_RE.match(name or "")
    if not m:
        return EngineSpec()
    text = m.group(3).lower()
    if "hybrid" in text or "electric/gas" in text:
        fuel = "hybrid"
    elif "flex" in text:
        fuel = "flex"
    elif "diesel" in text:
        fuel = "diesel"
    elif "electric" in text:
        fuel = "electric"
    else:
        fuel = "gas"
    return EngineSpec(float(m.group(1)), int(m.group(2)), fuel)


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def decoded_engine(raw: dict) -> EngineSpec:
    disp = _num(raw.get("DisplacementL"))
    cyl = _num(raw.get("EngineCylinders"))
    primary = (raw.get("FuelTypePrimary") or "").lower()
    secondary = (raw.get("FuelTypeSecondary") or "").lower()
    electrification = (raw.get("ElectrificationLevel") or "").lower()
    fuel = None
    if "hev" in electrification or "hybrid" in electrification:
        fuel = "hybrid"
    elif "e85" in secondary or "ethanol" in secondary or "flexible" in primary:
        fuel = "flex"
    elif "diesel" in primary:
        fuel = "diesel"
    elif "electric" in primary:
        fuel = "electric"
    elif "gasoline" in primary:
        fuel = "gas"
    return EngineSpec(round(disp, 1) if disp else None, int(cyl) if cyl else None, fuel)


def _narrow(rows, keep, label, out: Narrowed):
    kept = [r for r in rows if keep(r)]
    if kept and len(kept) < len(rows):
        out.narrowed_by.append(label)
        return kept
    return rows


def narrow(raw: dict, rows: list[CatalogueRow]) -> Narrowed:
    """Cut the year+make catalogue rows down to the cars this decode can be."""
    keys = model_keys(raw)
    rows = [r for r in rows if name_key(r.model) in keys]
    out = Narrowed(rows=[])
    if not rows:
        return out
    want = decoded_engine(raw)
    specs = {r.car_id: parse_catalogue_engine(r.engine) for r in rows}

    def disp_ok(r):
        d = specs[r.car_id].displacement_l
        return d is not None and abs(d - want.displacement_l) < 0.06

    if want.displacement_l is not None and want.cylinders is not None:
        rows = _narrow(rows, lambda r: disp_ok(r) and specs[r.car_id].cylinders == want.cylinders, "engine", out)
    elif want.displacement_l is not None:
        rows = _narrow(rows, disp_ok, "engine", out)
    if want.fuel:
        rows = _narrow(rows, lambda r: specs[r.car_id].fuel == want.fuel, "fuel", out)
    trims = {t.strip().lower() for t in (raw.get("Trim"), raw.get("Series")) if t and t.strip()}
    if trims:
        rows = _narrow(rows, lambda r: (r.trim or "").strip().lower() in trims, "trim", out)
    out.rows = sorted(rows, key=lambda r: r.car_id)
    return out


def summary(raw: dict) -> dict:
    """The decode fields the garage shows."""
    spec = decoded_engine(raw)
    error_code = (raw.get("ErrorCode") or "").strip()
    return {
        "year": (raw.get("ModelYear") or "").strip() or None,
        "make": (raw.get("Make") or "").strip() or None,
        "model": (raw.get("Model") or "").strip() or None,
        "trim": (raw.get("Trim") or "").strip() or None,
        "series": (raw.get("Series") or "").strip() or None,
        "displacement_l": spec.displacement_l,
        "cylinders": spec.cylinders,
        "fuel": spec.fuel,
        "drive": (raw.get("DriveType") or "").strip() or None,
        "body": (raw.get("BodyClass") or "").strip() or None,
        # NHTSA "0" = clean decode; anything else is a warning (e.g. "1" check digit wrong), shown not blocking
        "error_code": error_code or None,
        "error_text": None if error_code in ("", "0") else (raw.get("ErrorText") or "").strip() or None,
    }
