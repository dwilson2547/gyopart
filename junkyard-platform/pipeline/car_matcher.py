"""
Narrow an NHTSA VIN decode to the parts_interchange cars it can be.

A catalogue car is year + make + model + trim + engine. The decode always gives year/make/model; it usually
gives engine displacement and cylinders, often fuel, sometimes a trim that matches the catalogue's. Each filter
is applied only when it keeps at least one car, so a sparse decode leaves a wider candidate set instead of an
empty one. One candidate left = exact match; more = "likely" (the vehicle is one of these).

Decode mappings (admin-rewrite-design §2.2) widen the names a decode may mean: a mapping for the decode's
make/model[/series] adds its catalogue make/model, possibly of another make. When nothing matches, the match
carries the reason, so the admin app can tell a fixable name mismatch from a catalogue gap.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from pipeline.pi_schema import (
    pi_car_table, pi_engine_table, pi_make_table, pi_model_table, pi_trim_table, pi_year_table,
)

# Catalogue engine names: "2.4L L4 - Gas", "3.5L V6 - Electric/Gas", "1.8L L4 - FULL HYBRID EV-GAS (FHEV)"
_ENGINE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)L\s+[A-Z]+(\d+)\s*-\s*(.+?)\s*$", re.IGNORECASE)


@dataclass
class EngineSpec:
    displacement_l: float | None = None
    cylinders: int | None = None
    fuel: str | None = None  # gas | flex | diesel | hybrid | electric | lpg | cng


# Why a decode matched no catalogue car. (no_vin is set by the pipeline, which knows the vehicle.)
DECODE_FAILED = "decode_failed"                    # no year, make or model in the decode
MAKE_NOT_IN_CATALOGUE = "make_not_in_catalogue"    # the catalogue has no car of that make in any year
YEAR_NOT_IN_CATALOGUE = "year_not_in_catalogue"    # the make, but not in that year
MODEL_NOT_IN_CATALOGUE = "model_not_in_catalogue"  # the make and year, but no model by that name, ever
MODEL_YEAR_GAP = "model_year_gap"                  # the model exists for the make, just not in that year


@dataclass
class CarMatch:
    candidates: list[int] = field(default_factory=list)
    narrowed_by: list[str] = field(default_factory=list)  # which filters cut the set: engine, fuel, trim
    reason: str | None = None   # set when candidates is empty
    mapped: bool = False        # a decode mapping supplied the matching name

    @property
    def exact(self) -> bool:
        return len(self.candidates) == 1


@dataclass(frozen=True)
class Mapping:
    """What the matcher needs of a DecodeMapping row (plain, so it outlives the session that loaded it)."""
    make_key: str
    model_key: str
    series_key: str | None
    year_from: int | None
    year_to: int | None
    catalogue_make: str
    catalogue_model: str

    @classmethod
    def of(cls, row) -> "Mapping":
        return cls(row.make_key, row.model_key, row.series_key, row.year_from, row.year_to,
                   row.catalogue_make, row.catalogue_model)


def parse_catalogue_engine(name: str | None) -> EngineSpec:
    m = _ENGINE_RE.match(name or "")
    if not m:
        return EngineSpec()
    fuel_text = m.group(3).lower()
    if "hybrid" in fuel_text or "electric/gas" in fuel_text:
        fuel = "hybrid"
    elif "flex" in fuel_text:
        fuel = "flex"
    elif "diesel" in fuel_text:
        fuel = "diesel"
    elif "lpg" in fuel_text:
        fuel = "lpg"
    elif "cng" in fuel_text:
        fuel = "cng"
    elif "electric" in fuel_text:
        fuel = "electric"
    else:
        fuel = "gas"
    return EngineSpec(float(m.group(1)), int(m.group(2)), fuel)


def _num(raw) -> float | None:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def decoded_engine(raw: dict) -> EngineSpec:
    """Engine spec from an NHTSA DecodeVINValues result row."""
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


_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def name_key(name: str | None) -> str:
    """Loose name key: 'Town and Country' == 'Town & Country', 'F-150' == 'F150'."""
    return _NON_ALNUM.sub("", (name or "").lower().replace("&", "and"))


def decoded_model_keys(raw: dict) -> set[str]:
    """Catalogue model names the decode may mean: NHTSA lists some as 'Caravan/Grand Caravan', and gives
    Ram pickups as Model 'Ram' + Series '1500' where the catalogue says 'Ram 1500'."""
    model = (raw.get("Model") or "").strip()
    series = (raw.get("Series") or "").strip()
    names = {model, *model.split("/")}
    if series:
        names |= {f"{n} {series}" for n in list(names)}
    return {name_key(n) for n in names if n.strip()}


def applicable_mappings(raw: dict, mappings) -> list[Mapping]:
    """The mappings that cover this decode: same make and model key, the series if the mapping names one,
    and the year inside its range."""
    make, model = name_key(raw.get("Make")), name_key(raw.get("Model"))
    series = name_key(raw.get("Series"))
    try:
        year = int((raw.get("ModelYear") or "").strip())
    except ValueError:
        year = None
    out = []
    for m in mappings:
        if m.make_key != make or m.model_key != model:
            continue
        if m.series_key and m.series_key != series:
            continue
        if year is not None and ((m.year_from and year < m.year_from) or (m.year_to and year > m.year_to)):
            continue
        out.append(m)
    return out


def _narrow(rows: list, keep, label: str, match: CarMatch) -> list:
    kept = [r for r in rows if keep(r)]
    if kept and len(kept) < len(rows):
        match.narrowed_by.append(label)
        return kept
    return rows


def _why_unmatched(conn, makes: set[str], pairs: set[tuple[str, str]], year_had_cars: bool) -> str:
    """Classify a decode no catalogue car fits. Only runs on a miss, so a match costs no extra queries."""
    if not year_had_cars:
        any_car = conn.execute(
            select(pi_car_table.c.id)
            .join(pi_make_table, pi_make_table.c.id == pi_car_table.c.make_id)
            .where(func.lower(pi_make_table.c.name).in_(makes))
            .limit(1)
        ).first()
        return YEAR_NOT_IN_CATALOGUE if any_car else MAKE_NOT_IN_CATALOGUE
    names = conn.execute(
        select(pi_make_table.c.name, pi_model_table.c.name)
        .join(pi_make_table, pi_make_table.c.id == pi_model_table.c.make_id)
        .where(func.lower(pi_make_table.c.name).in_(makes))
        .distinct()
    ).all()
    if any((mk.lower(), name_key(md)) in pairs for mk, md in names):
        return MODEL_YEAR_GAP
    return MODEL_NOT_IN_CATALOGUE


def match_decoded(raw: dict, pi_engine: Engine, mappings=()) -> CarMatch:
    """Candidate car ids for a decoded VIN. Empty (with `reason`) when no catalogue car fits."""
    year = (raw.get("ModelYear") or "").strip()
    make = (raw.get("Make") or "").strip()
    model = (raw.get("Model") or "").strip()
    match = CarMatch()
    if not (year and make and model):
        match.reason = DECODE_FAILED
        return match

    # The (make, model key) pairs this decode may mean: its own names, plus any mapping's catalogue names.
    pairs = {(make.lower(), k) for k in decoded_model_keys(raw)}
    mapped_pairs = {(m.catalogue_make.lower(), name_key(m.catalogue_model)) for m in applicable_mappings(raw, mappings)}
    pairs |= mapped_pairs
    makes = {mk for mk, _ in pairs}

    with pi_engine.connect() as conn:
        year_rows = conn.execute(
            select(pi_car_table.c.id, pi_trim_table.c.name.label("trim"), pi_engine_table.c.name.label("engine"))
            .join(pi_year_table, pi_year_table.c.id == pi_car_table.c.year_id)
            .join(pi_make_table, pi_make_table.c.id == pi_car_table.c.make_id)
            .join(pi_model_table, pi_model_table.c.id == pi_car_table.c.model_id)
            .outerjoin(pi_trim_table, pi_trim_table.c.id == pi_car_table.c.trim_id)
            .outerjoin(pi_engine_table, pi_engine_table.c.id == pi_car_table.c.engine_id)
            .add_columns(pi_model_table.c.name.label("model"), pi_make_table.c.name.label("make"))
            .where(pi_year_table.c.name == year, func.lower(pi_make_table.c.name).in_(makes))
        ).all()
        rows = [r for r in year_rows if (r.make.lower(), name_key(r.model)) in pairs]
        if not rows:
            match.reason = _why_unmatched(conn, makes, pairs, bool(year_rows))
            return match
    match.mapped = any((r.make.lower(), name_key(r.model)) in mapped_pairs for r in rows)

    want = decoded_engine(raw)
    specs = {r.id: parse_catalogue_engine(r.engine) for r in rows}
    if want.displacement_l is not None and want.cylinders is not None:
        rows = _narrow(rows, lambda r: specs[r.id].displacement_l is not None
                       and abs(specs[r.id].displacement_l - want.displacement_l) < 0.06
                       and specs[r.id].cylinders == want.cylinders, "engine", match)
    elif want.displacement_l is not None:
        rows = _narrow(rows, lambda r: specs[r.id].displacement_l is not None
                       and abs(specs[r.id].displacement_l - want.displacement_l) < 0.06, "engine", match)
    if want.fuel:
        rows = _narrow(rows, lambda r: specs[r.id].fuel == want.fuel, "fuel", match)

    trims = {t.strip().lower() for t in (raw.get("Trim"), raw.get("Series")) if t and t.strip()}
    if trims:
        rows = _narrow(rows, lambda r: (r.trim or "").strip().lower() in trims, "trim", match)

    match.candidates = sorted(r.id for r in rows)
    return match


_DRIVE = (("4wd", "4WD"), ("4x4", "4WD"), ("awd", "AWD"), ("all-wheel", "AWD"),
          ("fwd", "FWD"), ("front-wheel", "FWD"), ("rwd", "RWD"), ("rear-wheel", "RWD"))
_FUEL_CODE = {"gas": "G", "flex": "G", "diesel": "D", "electric": "E", "hybrid": "H"}


def decoded_vehicle_fields(raw: dict) -> dict:
    """Vehicle columns the decode can fill (only applied where the scraper left them empty)."""
    out: dict = {}
    spec = decoded_engine(raw)
    if spec.displacement_l:
        out["engine_size"] = spec.displacement_l
    if spec.cylinders:
        out["engine_cylinders"] = spec.cylinders
    if spec.fuel in _FUEL_CODE:
        out["fuel_type"] = _FUEL_CODE[spec.fuel]
    config = (raw.get("EngineConfiguration") or "").lower()
    if config.startswith("v"):
        out["engine_block"] = "V"
    elif "in-line" in config or "inline" in config:
        out["engine_block"] = "I"
    elif "horizontal" in config or "opposed" in config:
        out["engine_block"] = "H"
    turbo = (raw.get("Turbo") or "").lower()
    if turbo in ("yes", "no"):
        out["engine_aspiration"] = "T" if turbo == "yes" else "N/A"
    drive = (raw.get("DriveType") or "").lower()
    for needle, code in _DRIVE:
        if needle in drive:
            out["drive_type"] = code
            break
    if raw.get("BodyClass"):
        out["body_type"] = raw["BodyClass"][:100]
    if raw.get("VehicleType"):
        out["vehicle_type"] = raw["VehicleType"][:100]
    doors = _num(raw.get("Doors"))
    if doors:
        out["doors"] = int(doors)
    if raw.get("Trim"):
        out["trim"] = raw["Trim"][:200]
    return out
