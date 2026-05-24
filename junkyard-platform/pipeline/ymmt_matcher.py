import re
from dataclasses import dataclass

from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.engine import Engine

from pipeline.pi_schema import (
    pi_car_table, pi_make_table, pi_model_table, pi_year_table,
)

_SUFFIXES = re.compile(r"\b(inc|corp|ltd|llc|co)\b\.?", re.IGNORECASE)
_PUNCT = re.compile(r"[^\w\s]")


def normalize(s: str) -> str:
    s = s.lower()
    s = _PUNCT.sub(" ", s)
    s = _SUFFIXES.sub("", s)
    return " ".join(s.split())


@dataclass
class YmmtMatch:
    car_id: int
    confidence: float
    make_match: str
    make_score: float
    model_match: str
    model_score: float


def match_car(
    year: int | None,
    raw_make: str,
    raw_model: str,
    pi_engine: Engine,
    threshold: float = 0.85,
) -> YmmtMatch | None:
    """Fuzzy-match raw make/model against parts_interchange. Returns YmmtMatch or None."""
    norm_make = normalize(raw_make)
    norm_model = normalize(raw_model)

    with pi_engine.connect() as conn:
        makes = conn.execute(select(pi_make_table.c.id, pi_make_table.c.name)).all()
        if not makes:
            return None

        make_names = [normalize(m.name) for m in makes]
        best_make = process.extractOne(norm_make, make_names, scorer=fuzz.WRatio)
        if not best_make or best_make[1] < threshold * 100:
            return None

        make_score = best_make[1] / 100.0
        make_idx = make_names.index(best_make[0])
        make_id = makes[make_idx].id
        make_match_name = makes[make_idx].name

        models = conn.execute(
            select(pi_model_table.c.id, pi_model_table.c.name)
            .where(pi_model_table.c.make_id == make_id)
        ).all()
        if not models:
            return None

        model_names = [normalize(m.name) for m in models]
        best_model = process.extractOne(norm_model, model_names, scorer=fuzz.WRatio)
        if not best_model or best_model[1] < threshold * 100:
            return None

        model_score = best_model[1] / 100.0
        model_idx = model_names.index(best_model[0])
        model_id = models[model_idx].id
        model_match_name = models[model_idx].name
        confidence = min(make_score, model_score)

        # Prefer year-specific car; fall back to any car with this make+model
        car_id = None
        if year:
            year_row = conn.execute(
                select(pi_year_table.c.id).where(pi_year_table.c.name == str(year))
            ).one_or_none()
            if year_row:
                car_row = conn.execute(
                    select(pi_car_table.c.id).where(
                        pi_car_table.c.year_id == year_row[0],
                        pi_car_table.c.make_id == make_id,
                        pi_car_table.c.model_id == model_id,
                    )
                ).first()
                if car_row:
                    car_id = car_row[0]

        if car_id is None:
            car_row = conn.execute(
                select(pi_car_table.c.id).where(
                    pi_car_table.c.make_id == make_id,
                    pi_car_table.c.model_id == model_id,
                )
            ).first()
            if car_row:
                car_id = car_row[0]

        if car_id is None:
            return None

        return YmmtMatch(
            car_id=car_id,
            confidence=confidence,
            make_match=make_match_name,
            make_score=make_score,
            model_match=model_match_name,
            model_score=model_score,
        )
