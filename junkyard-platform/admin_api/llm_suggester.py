"""
LLM Rule Suggester — batch job that queries unresolved discrepancy groups,
calls the Anthropic API to suggest normalization rules, and inserts them as
pending (is_active=False) MappingRule rows.

CLI:
  python -m admin_api.llm_suggester [--batch-size 20] [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime
import json
import logging
import os

import anthropic
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from admin_api.discrepancies import get_grouped_discrepancies
from junkyard_common.db import get_engine
from junkyard_common.models import MappingDiscrepancy, MappingRule

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

MIN_CONFIDENCE = 0.80


def fetch_canonical_makes(pi_engine) -> list[str]:
    with pi_engine.connect() as conn:
        rows = conn.execute(text("SELECT name FROM make ORDER BY name")).fetchall()
    return [r[0] for r in rows]


def build_prompt(groups: list[dict], canonical_makes: list[str]) -> str:
    makes_str = ", ".join(canonical_makes[:100])
    lines = [
        f"{i}. source={g['source']!r} make={g['raw_make']!r} model={g['raw_model']!r} count={g['count']}"
        for i, g in enumerate(groups)
    ]
    groups_str = "\n".join(lines)
    return f"""You are a vehicle data normalization assistant. Analyze these junkyard inventory groups with non-standard make/model strings and suggest normalization mapping rules.

Canonical car makes in our database: {makes_str}

Groups to normalize (index, source, raw make, raw model, vehicle count):
{groups_str}

For each group you can confidently normalize, respond with a JSON object:
{{
  "suggestions": [
    {{
      "group_index": 0,
      "field": "make",
      "rule_type": "exact",
      "raw_value": "CHEV",
      "canonical_value": "Chevrolet",
      "make_context": null,
      "confidence": 0.95,
      "rationale": "CHEV is a well-known abbreviation for Chevrolet"
    }}
  ]
}}

Rules:
- field: "make", "model", or "trim"
- rule_type: "exact" (full string match), "prefix" (starts-with), or "regex"
- make_context: fill in the canonical make if this is a model/trim rule
- confidence: 0.0-1.0, only include suggestions with confidence >= {MIN_CONFIDENCE}
- You may suggest multiple rules per group
- Omit groups you cannot confidently normalize
- Respond ONLY with the JSON object, no other text"""


def parse_llm_response(raw_response: str, groups: list[dict]) -> list[dict]:
    try:
        data = json.loads(raw_response.strip())
    except (json.JSONDecodeError, ValueError):
        logger.warning("LLM response was not valid JSON")
        return []

    results = []
    for s in data.get("suggestions", []):
        if s.get("confidence", 0) < MIN_CONFIDENCE:
            continue
        idx = s.get("group_index")
        if idx is None or idx >= len(groups):
            continue
        group = groups[idx]
        results.append({
            "field": s["field"],
            "rule_type": s["rule_type"],
            "raw_value": s["raw_value"],
            "canonical_value": s["canonical_value"],
            "make_context": s.get("make_context"),
            "llm_confidence": s["confidence"],
            "llm_rationale": s.get("rationale", ""),
            "source": group["source"],
            "affected_vehicle_ids": group["vehicle_ids"],
            "count": group["count"],
        })
    return results


def insert_suggestions(engine, suggestions: list[dict], dry_run: bool) -> int:
    if dry_run:
        logger.info("[dry-run] Would insert %d suggestions", len(suggestions))
        return len(suggestions)

    now = datetime.datetime.utcnow()
    inserted = 0
    with Session(engine) as session:
        for s in suggestions:
            rule = MappingRule(
                scope="global",
                field=s["field"],
                rule_type=s["rule_type"],
                raw_value=s["raw_value"],
                canonical_value=s["canonical_value"],
                make_context=s.get("make_context"),
                priority=100,
                is_active=False,
                created_by="llm_suggested",
                created_at=now,
                applied_count=0,
                llm_confidence=s["llm_confidence"],
                llm_rationale=s["llm_rationale"],
            )
            session.add(rule)
            session.flush()

            for vid in s["affected_vehicle_ids"]:
                d = session.execute(
                    select(MappingDiscrepancy).where(
                        MappingDiscrepancy.vehicle_id == vid,
                        MappingDiscrepancy.status == "unresolved",
                    )
                ).scalar_one_or_none()
                if d:
                    d.status = "pending_rule"

            inserted += 1
        session.commit()

    logger.info("Inserted %d pending rule suggestions", inserted)
    return inserted


def run(batch_size: int = 20, dry_run: bool = False) -> None:
    ji_engine = get_engine()
    pi_url = os.environ.get("PARTS_DATABASE_URL")
    pi_engine = create_engine(pi_url) if pi_url else None

    canonical_makes = fetch_canonical_makes(pi_engine) if pi_engine else []
    groups = get_grouped_discrepancies(ji_engine, status="unresolved")

    if not groups:
        logger.info("No unresolved discrepancy groups — nothing to do")
        return

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

    total_inserted = 0
    for i in range(0, len(groups), batch_size):
        batch = groups[i : i + batch_size]
        prompt = build_prompt(batch, canonical_makes)
        logger.info("Sending batch %d-%d to LLM...", i, i + len(batch))

        try:
            message = client.messages.create(
                model=model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text
        except Exception as exc:
            logger.error("LLM call failed for batch %d: %s", i, exc)
            continue

        suggestions = parse_llm_response(raw, batch)
        logger.info("Batch %d: %d suggestions from LLM", i, len(suggestions))
        total_inserted += insert_suggestions(ji_engine, suggestions, dry_run)

    logger.info("Done. Total suggestions inserted: %d", total_inserted)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LLM rule suggester batch job")
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(batch_size=args.batch_size, dry_run=args.dry_run)
