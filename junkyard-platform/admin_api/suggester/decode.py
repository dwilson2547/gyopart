"""Decode groups: which catalogue model(s) an NHTSA decode (make, model, series, years) is.

bundle() gathers the decode's cars and up to MAX_CANDIDATES catalogue models of the decode's make (of any make when the
catalogue has none of that make: RAM trucks are Dodge's there, Geo is Chevrolet), each previewed as the only target (how many of the cars it would match, and to exactly one car); messages() renders it for the model;
check() turns the model's JSON reply into a mapping proposal, or says why none is filed.
"""
from __future__ import annotations

import re
from collections import Counter
from functools import lru_cache

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from junkyard_common.models import Vehicle, VinCache
from pipeline.car_matcher import Mapping, name_key
from pipeline.pi_schema import pi_car_table, pi_make_table, pi_model_table, pi_year_table

from ..api import catalogue
from ..api.common import sql_key, sql_year
from ..api.fixes import simulate_mapping

MAX_CANDIDATES = 15
MAX_NEW_TOKENS = 300
_EMPTY = {"", "Not Applicable", "null", "None"}
# Decode fields shown to the model, as the most common values among the cars.
_FIELDS = ("Trim", "BodyClass", "DriveType", "FuelTypePrimary")
_TOP = 5

_V1 = """\
You map car names between two databases for a junkyard parts search. NHTSA's VIN decoder names a car one way \
(make, model, series); the parts catalogue names it another way. A decode mapping says which catalogue model or \
models an NHTSA decode is, so the cars that carry it can be matched to catalogue cars and their parts.

You get one NHTSA decode, what its cars' decodes say, and a numbered list of candidate catalogue models. Each \
candidate has the years it exists in the catalogue and how many of these cars it would match on its own (the \
matcher also checks year, engine and fuel). Decide which candidates this decode is.

Rules:
- Pick only from the candidates, using their exact names.
- Pick every candidate the decode can be. NHTSA often names a family that the catalogue lists by variant: \
"C-Class" is the catalogue's "C 230", "C 240", "C 320" and so on; pick them all and the matcher chooses by year \
and engine. Never pick a different car that only shares letters or numbers with the name.
- A candidate counts only if it exists in the catalogue in the cars' years. Never pick one because it exists in \
other years.
- The series and the decodes' trims and bodies tell variants apart (series "2500 HD" points at an HD model; a \
cargo van body at the van model).
- If no candidate is this car, or you can't tell, the decision is "unsure". A wrong mapping makes cars show the \
wrong parts to buyers; "unsure" costs nothing.

Reply with JSON only, no other text: \
{"decision": "map" or "unsure", "targets": ["candidate name", ...], "reason": "one sentence"}"""

# Prompts by version; a suggestion records the one that made it. v1 (2026-10-30 bake-off) read "pick every
# candidate the decode can be" as licence to take whole families (Express 1500 -> 1500, 2500 and 3500).
_V2 = """\
You map car names between two databases for a junkyard parts search. NHTSA's VIN decoder names a car one way \
(make, model, series); the parts catalogue names it another way. A decode mapping says which catalogue model or \
models an NHTSA decode is, so the cars that carry it can be matched to catalogue cars and their parts.

You get one NHTSA decode, what its cars' decodes say, and a numbered list of candidate catalogue models. Each \
candidate has the years it exists in the catalogue and how many of these cars it would match on its own (the \
matcher also checks year, engine and fuel, so a wrong model can still match many cars). Decide which candidates \
this decode is.

Rules:
- Pick only from the candidates, using their exact names.
- The model and series together usually name one catalogue model: "Express" with series "1500 (1/2 Ton)" is \
"Express 1500"; "Transit" with series "250" is "Transit-250"; "Ram" with series "2500" is "Ram 2500". Pick that \
one. Words like "1/2 Ton", "3/4 Ton" or "Single Rear Wheel" only say which number it is. Never add the other \
numbers (2500, 3500) or a heavier "HD" model unless the decode says HD.
- When the series names a variant of the model ("Envoy" with series "XL", "Trailblazer" with "EXT", "E-150" with \
"Econoline"), pick the variant, and the plain model too if it is a candidate: the catalogue sometimes lists the \
variant's years under the plain name.
- When there is no series and the model names a family that the catalogue lists by variant ("C-Class" is "C 230", \
"C 240", "C 320" and so on), pick every variant that exists in the cars' years.
- Never pick a different car that only shares a number or letters with the decode: "Express 3500" is not \
"Silverado 3500 HD", "Sprinter 3500" or "LCF 3500"; "Transit-350" is not "Transit-350 HD".
- A candidate counts only if it exists in the catalogue in the cars' years.
- If no candidate is this car, or you can't tell, the decision is "unsure". A wrong mapping makes cars show the \
wrong parts to buyers; "unsure" costs nothing.

Reply with JSON only, no other text: \
{"decision": "map" or "unsure", "targets": ["candidate name", ...], "reason": "one sentence"}"""

# v2 won the bake-off with Qwen3-VL-4B (docs/matching-v2-design.md §4, phase 4).
# v3: v2 plus the other-make rule, for decodes whose make the catalogue doesn't have.
_V3 = _V2.replace(
    "- A candidate counts only if it exists in the catalogue in the cars' years.",
    "- When the catalogue has no cars of the decode's make, the candidates come from other makes. Pick one only when "
    "it is the same car sold under another brand name, or the brand that took the model over (NHTSA's make \"RAM\" "
    "is the catalogue's Dodge \"Ram 1500\"; Geo \"Prizm\" is Chevrolet \"Prizm\"). A model from an unrelated make "
    "with a similar name is a different car: answer unsure.\n"
    "- A candidate counts only if it exists in the catalogue in the cars' years.")

PROMPTS = {"decode-v1": _V1, "decode-v2": _V2, "decode-v3": _V3}
PROMPT = "decode-v3"
OTHER_MAKE_MIN_SCORE = 0.5


def spans(years: list[int]) -> str:
    """[2001, 2002, 2003, 2007] -> "2001–2003, 2007"."""
    out, start, prev = [], None, None
    for y in sorted(years):
        if start is None:
            start = y
        elif y != prev + 1:
            out.append(f"{start}–{prev}" if prev != start else str(start))
            start = y
        prev = y
    if start is not None:
        out.append(f"{start}–{prev}" if prev != start else str(start))
    return ", ".join(out) or "none"


def decode_rows(session: Session, make: str, model: str, series: str | None, year_from: int | None,
                year_to: int | None, unmatched_only: bool) -> list[tuple[int, dict, str | None, str]]:
    """Active vehicles whose cached decode is this one: (id, raw decode, yard trim, yard). The bake-off replays a
    mapping, so it takes every such vehicle, matched or not; a live group takes the unmatched ones."""
    series_col = func.coalesce(VinCache.raw["Series"].astext, "")
    year = sql_year(VinCache.model_year)
    q = (select(Vehicle.id, VinCache.raw, Vehicle.trim, Vehicle.source).join(VinCache, VinCache.vin == Vehicle.vin)
         .where(Vehicle.is_active.is_(True), sql_key(VinCache.make) == name_key(make),
                sql_key(VinCache.model) == name_key(model)))
    if series:
        q = q.where(sql_key(series_col) == name_key(series))
    if year_from:
        q = q.where(year >= year_from)
    if year_to:
        q = q.where(year <= year_to)
    if unmatched_only:
        q = q.where(Vehicle.car_id_resolved.is_(False))
    return [(vid, raw or {}, trim, src) for vid, raw, trim, src in session.execute(q)]


def _value(raw: dict, field: str) -> str | None:
    v = raw.get(field)
    return None if v is None or str(v).strip() in _EMPTY else str(v).strip()


def _engine(raw: dict) -> str | None:
    d, c = _value(raw, "DisplacementL"), _value(raw, "EngineCylinders")
    if not d and not c:
        return None
    return " ".join(p for p in (f"{float(d):.1f}L" if d and d.replace(".", "", 1).isdigit() else d,
                                f"{c} cyl" if c else None) if p)


@lru_cache(maxsize=4)
def _all_models(pi) -> list[tuple[str, str, list[int]]]:
    """Every catalogue (make, model, years): the candidates when the decode's make isn't in the catalogue."""
    with pi.connect() as conn:
        rows = conn.execute(select(pi_make_table.c.name, pi_model_table.c.name, catalogue._YEAR).distinct()
                            .join(pi_model_table, pi_model_table.c.make_id == pi_make_table.c.id)
                            .join(pi_car_table, pi_car_table.c.model_id == pi_model_table.c.id)
                            .join(pi_year_table, pi_year_table.c.id == pi_car_table.c.year_id)).all()
    years: dict[tuple, set] = {}
    for mk, md, y in rows:
        years.setdefault((mk, md), set()).add(y)
    return [(mk, md, sorted(ys)) for (mk, md), ys in sorted(years.items())]


def other_make_candidates(pi, names: list[str], lo, hi, limit: int = MAX_CANDIDATES) -> list[dict]:
    """Catalogue models of any make, ranked like catalogue.suggest, comparing "make model" as well as the model."""
    out = []
    for mk, md, years in _all_models(pi):
        score = max((catalogue.similarity(n, t) for n in names if n for t in (md, f"{mk} {md}")), default=0.0)
        if score >= OTHER_MAKE_MIN_SCORE:
            out.append({"make": mk, "name": md, "years": years, "score": score,
                        "yearsInRange": catalogue._in_range(years, lo, hi)})
    out.sort(key=lambda m: (m["yearsInRange"] > 0, m["score"]), reverse=True)
    return out[:limit]


def bundle(pi, make: str, model: str, series: str | None, year_from: int | None, year_to: int | None,
           rows: list[tuple[int, dict, str | None, str]], mappings: list[Mapping]) -> dict:
    """Everything the model sees for one decode, candidates previewed against `mappings` (the other mappings in
    force: a replay leaves out the one being replayed)."""
    raws, trims = [r[1] for r in rows], [r[2] for r in rows]
    years = Counter(int(y) for r in raws if (y := _value(r, "ModelYear")) and y.isdigit())
    lo, hi = (min(years), max(years)) if years else (year_from, year_to)
    fields = {f: Counter(v for r in raws if (v := _value(r, f))).most_common(_TOP) for f in _FIELDS}
    fields["engine"] = Counter(e for r in raws if (e := _engine(r))).most_common(_TOP)
    cat = catalogue.catalogue_make(pi, make)
    names = [f"{model} {series}" if series else None, model]
    if cat:
        ranked = [{**c, "make": cat} for c in catalogue.suggest(pi, cat, names, lo, hi, limit=MAX_CANDIDATES)]
    else:
        ranked = other_make_candidates(pi, [f"{make} {n}" for n in names if n] + names, lo, hi)
    mk, md, sk = name_key(make), name_key(model), name_key(series) if series else None
    cands = []
    for c in ranked:
        p = simulate_mapping(pi, raws, mappings + [Mapping(mk, md, sk, year_from, year_to, c["make"], c["name"])], trims)
        cands.append({"make": c["make"], "model": c["name"], "years": spans(c["years"]),
                      "yearsInRange": c["yearsInRange"], "score": c["score"], "wouldMatch": p["wouldMatch"],
                      "exact": p["exact"]})
    return {"kind": "decode", "prompt": PROMPT,
            "decode": {"make": make, "model": model, "series": series, "yearFrom": year_from, "yearTo": year_to},
            "vehicles": len(rows), "yards": len({r[3] for r in rows}), "byYear": dict(sorted(years.items())),
            "fields": {k: v for k, v in fields.items() if v}, "catalogueMake": cat, "candidates": cands}


def messages(b: dict, prompt: str = PROMPT) -> list[dict]:
    d = b["decode"]
    lines = [f'NHTSA decode: make "{d["make"]}", model "{d["model"]}", '
             + (f'series "{d["series"]}"' if d["series"] else "any series"),
             f'Cars: {b["vehicles"]} at {b["yards"]} yards, model years '
             + ", ".join(f"{y} ({n})" for y, n in b["byYear"].items())]
    for f, vals in b["fields"].items():
        lines.append(f"{f}: " + ", ".join(f"{v} ({n})" for v, n in vals))
    if b["catalogueMake"]:
        lines.append(f'Candidate {b["catalogueMake"]} models:')
    else:
        lines.append(f'The catalogue has no cars of make "{d["make"]}". Candidate models of other makes:')
    for i, c in enumerate(b["candidates"], 1):
        name = f'"{c["model"]}"' if b["catalogueMake"] else f'{c["make"]} "{c["model"]}"'
        lines.append(f'{i}. {name}: in the catalogue {c["years"]}; would match {c["wouldMatch"]} of '
                     f'{b["vehicles"]} cars ({c["exact"]} to exactly one car)')
    if not b["candidates"]:
        lines.append("(none with a similar name)")
    return [{"role": "system", "content": PROMPTS[prompt]}, {"role": "user", "content": "\n".join(lines)}]


# Truck weight classes, as NHTSA's series spells them, and the model number each one is.
_TON = re.compile(r"\b(1/2|3/4|1)\s*-?\s*ton\b", re.IGNORECASE)
_TON_NUMBER = {"1/2": "1500", "3/4": "2500", "1": "3500"}
_WEIGHT_NUMBER = re.compile(r"(?<!\d)(1500|2500|3500)(?!\d)")
# A lettered model number ("F-550", "E-450"); compared only with a target of the same letters, so a platform code
# ("GMT-400") or a different family ("C1500") never counts.
_MODEL_NUMBER = re.compile(r"\b([A-Za-z]{1,2})-?\s?(\d{3,4})(?!\d)")


def number_conflict(d: dict, target: str) -> str | None:
    """Why `target` can't be this decode by the numbers in the names, or None. Two objective cases the model gets
    wrong: a weight class in the series that the target's number contradicts ("3/4 Ton" is a 2500, never a 1500 or
    3500), and a lettered model number that the target's differs from (an F-550 isn't an F-350)."""
    ton = _TON.search(d.get("series") or "")
    picked = _WEIGHT_NUMBER.search(target)
    if ton and picked and picked.group(1) != _TON_NUMBER[ton.group(1)]:
        return f'series "{d["series"]}" is a {_TON_NUMBER[ton.group(1)]}, not "{target}"'
    own = _MODEL_NUMBER.search(d.get("model") or "")
    theirs = _MODEL_NUMBER.search(target)
    if own and theirs and own.group(1).lower() == theirs.group(1).lower() and own.group(2) != theirs.group(2):
        return f'"{target}" has a different model number from "{d["model"]}"'
    return None


def check(pi, b: dict, reply: dict | None, rows=None, mappings=None) -> dict:
    """The model's reply -> {"decision": "map", "targets": [{make, model}], "reason"} with the combined preview when
    `rows`/`mappings` are given; or {"decision": "unsure" | "refused" | "invalid", "reason"}. Only "map" is filed."""
    if not isinstance(reply, dict):
        return {"decision": "invalid", "reason": "the reply wasn't the JSON asked for"}
    decision, reason = reply.get("decision"), str(reply.get("reason") or "")[:500]
    if decision == "unsure":
        return {"decision": "unsure", "reason": reason}
    if decision != "map":
        return {"decision": "invalid", "reason": f"decision {decision!r} isn't map or unsure"}
    targets = reply.get("targets")
    if not isinstance(targets, list) or not targets or not all(isinstance(t, str) for t in targets):
        return {"decision": "invalid", "reason": "a map decision needs a list of candidate names"}
    # By "make model", and by model alone where only one make has that name (other-make lists can repeat one).
    by_full = {name_key(f'{c["make"]} {c["model"]}'): c for c in b["candidates"]}
    names = Counter(name_key(c["model"]) for c in b["candidates"])
    by_model = {name_key(c["model"]): c for c in b["candidates"] if names[name_key(c["model"])] == 1}
    picked = []
    for t in targets:
        c = by_full.get(name_key(t)) or by_model.get(name_key(t))
        if c is None:
            return {"decision": "refused", "reason": f'"{t}" is not one of the candidates'}
        if not c["yearsInRange"]:
            return {"decision": "refused", "reason": f'"{c["model"]}" isn\'t in the catalogue in the cars\' years'}
        if why := number_conflict(b["decode"], c["model"]):
            return {"decision": "refused", "reason": why}
        if c not in picked:
            picked.append(c)
    out = {"decision": "map", "targets": [{"make": c["make"], "model": c["model"]} for c in picked], "reason": reason}
    if rows is not None and mappings is not None:
        d = b["decode"]
        mk, md = name_key(d["make"]), name_key(d["model"])
        sk = name_key(d["series"]) if d["series"] else None
        extra = [Mapping(mk, md, sk, d["yearFrom"], d["yearTo"], c["make"], c["model"]) for c in picked]
        p = simulate_mapping(pi, [r[1] for r in rows], mappings + extra, [r[2] for r in rows])
        if not p["wouldMatch"]:
            return {"decision": "refused", "reason": "together the targets match none of the cars"}
        out["preview"] = p
    return out
