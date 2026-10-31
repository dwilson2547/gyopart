"""Decode groups: which catalogue model(s) an NHTSA decode (make, model, series, years) is.

bundle() gathers the decode's cars and up to MAX_CANDIDATES catalogue models of the decode's make, each previewed as
the only target (how many of the cars it would match, and to exactly one car); messages() renders it for the model;
check() turns the model's JSON reply into a mapping proposal, or says why none is filed.
"""
from __future__ import annotations

from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from junkyard_common.models import Vehicle, VinCache
from pipeline.car_matcher import Mapping, name_key

from ..api import catalogue
from ..api.common import sql_key, sql_year
from ..api.fixes import simulate_mapping

PROMPT = "decode-v1"
MAX_CANDIDATES = 15
MAX_NEW_TOKENS = 300
_EMPTY = {"", "Not Applicable", "null", "None"}
# Decode fields shown to the model, as the most common values among the cars.
_FIELDS = ("Trim", "BodyClass", "DriveType", "FuelTypePrimary")
_TOP = 5

SYSTEM = """\
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
    cands = []
    if cat:
        names = [f"{model} {series}" if series else None, model]
        mk, md, sk = name_key(make), name_key(model), name_key(series) if series else None
        for c in catalogue.suggest(pi, cat, names, lo, hi, limit=MAX_CANDIDATES):
            p = simulate_mapping(pi, raws, mappings + [Mapping(mk, md, sk, year_from, year_to, cat, c["name"])], trims)
            cands.append({"make": cat, "model": c["name"], "years": spans(c["years"]), "yearsInRange": c["yearsInRange"],
                          "score": c["score"], "wouldMatch": p["wouldMatch"], "exact": p["exact"]})
    return {"kind": "decode", "prompt": PROMPT,
            "decode": {"make": make, "model": model, "series": series, "yearFrom": year_from, "yearTo": year_to},
            "vehicles": len(rows), "yards": len({r[3] for r in rows}), "byYear": dict(sorted(years.items())),
            "fields": {k: v for k, v in fields.items() if v}, "catalogueMake": cat, "candidates": cands}


def messages(b: dict) -> list[dict]:
    d = b["decode"]
    lines = [f'NHTSA decode: make "{d["make"]}", model "{d["model"]}", '
             + (f'series "{d["series"]}"' if d["series"] else "any series"),
             f'Cars: {b["vehicles"]} at {b["yards"]} yards, model years '
             + ", ".join(f"{y} ({n})" for y, n in b["byYear"].items())]
    for f, vals in b["fields"].items():
        lines.append(f"{f}: " + ", ".join(f"{v} ({n})" for v, n in vals))
    if not b["catalogueMake"]:
        lines.append(f'The catalogue has no make called "{d["make"]}", so there are no candidates.')
    else:
        lines.append(f'Candidate {b["catalogueMake"]} models:')
        for i, c in enumerate(b["candidates"], 1):
            lines.append(f'{i}. "{c["model"]}": in the catalogue {c["years"]}; would match {c["wouldMatch"]} of '
                         f'{b["vehicles"]} cars ({c["exact"]} to exactly one car)')
        if not b["candidates"]:
            lines.append("(none with a similar name)")
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "\n".join(lines)}]


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
    by_key = {name_key(c["model"]): c for c in b["candidates"]}
    picked = []
    for t in targets:
        c = by_key.get(name_key(t)) or by_key.get(name_key(t.removeprefix(b["catalogueMake"] or "")))
        if c is None:
            return {"decision": "refused", "reason": f'"{t}" is not one of the candidates'}
        if not c["yearsInRange"]:
            return {"decision": "refused", "reason": f'"{c["model"]}" isn\'t in the catalogue in the cars\' years'}
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
