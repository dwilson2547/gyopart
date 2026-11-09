"""One suggester run (matching-v2-design §3.4): every open fixable decode group that is due gets one model call;
what passes the check is filed as a suggestion for review, everything else is recorded with its reason.

    python -m admin_api.suggester.run [--trigger schedule|manual] [--limit N] [--min-vehicles N]
    python -m admin_api.suggester.run --export cases.jsonl      # the due groups' model inputs, nothing written
    python -m admin_api.suggester.run --replies replies.jsonl --dry-run   # replies from a file; print, write nothing

A group is due when it has no suggestion waiting or rejected, and its last attempt was with a different model,
prompt or number of open vehicles (the model decodes greedily: the same bundle gets the same answer). Groups go
biggest first. Only decode groups so far; trim and yard prompts have no labels to be tested against yet.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from collections import Counter
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from junkyard_common.models import FixSuggestion, SuggesterAttempt, SuggesterRun, Vehicle
from pipeline.resolution_pipeline import load_mappings

from . import decode
from .gpu import GpuClient
from ..api import discrepancies, fixes, suggestions
from ..api.common import BUCKETS
from ..api.discrepancies import GroupKey

MODEL = os.environ.get("SUGGESTER_GPU_MODEL", "qwen3vl")
KIND = "decode_mapping"
FILED_BY = "suggester"


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def due_groups(s: Session, model: str, prompt: str, min_vehicles: int, limit: int) -> list[tuple[GroupKey, int]]:
    rows = discrepancies._group_rows(s, "decode", BUCKETS["fixable"], "open", None, None, None)
    rows.sort(key=lambda g: (-g["vehicles"], str(g["key"])))
    out = []
    for g in rows:
        if g["vehicles"] < min_vehicles or len(out) >= limit:
            break
        key = GroupKey(**g["key"])
        ref = suggestions.group_ref(key)
        if s.execute(select(FixSuggestion.id).where(
                FixSuggestion.group_ref == ref,
                FixSuggestion.status.in_((suggestions.PENDING, suggestions.REJECTED))).limit(1)).first():
            continue
        last = s.execute(select(SuggesterAttempt).where(SuggesterAttempt.group_ref == ref)
                         .order_by(SuggesterAttempt.id.desc()).limit(1)).scalars().first()
        if last and (last.model, last.prompt, last.vehicles) == (model, prompt, g["vehicles"]):
            continue
        out.append((key, g["vehicles"]))
    return out


def proposal(key: GroupKey, targets: list[dict]) -> dict:
    return {"make": key.make, "model": key.model, "series": key.series or None, "year_from": None, "year_to": None,
            "targets": targets}


def gather(s: Session, pi, groups: list[tuple[GroupKey, int]]) -> list[dict]:
    """Each group's cars, bundle and model input."""
    mappings = load_mappings(s)
    out = []
    for key, n in groups:
        # The cars a mapping for this group would cover: open, unmatched, and (when the group has no series) every
        # series of the decode, as the fix forms do.
        req = SimpleNamespace(make=key.make, model=key.model, series=key.series or None, year_from=None, year_to=None)
        cars = fixes.mapping_vehicles(s, req)
        yard = dict(s.execute(select(Vehicle.id, Vehicle.source).where(Vehicle.id.in_([c[0] for c in cars]))).all())
        rows = [(vid, raw, trim, yard.get(vid, "")) for vid, raw, trim in cars]
        b = decode.bundle(pi, key.make, key.model, key.series or None, None, None, rows, mappings)
        out.append({"key": key, "vehicles": n, "rows": rows, "bundle": b, "mappings": mappings,
                    "input": {"messages": decode.messages(b), "json": True, "max_new_tokens": decode.MAX_NEW_TOKENS}})
    return out


def decide(eng, item: dict, reply: dict) -> tuple[str, str, int | None]:
    """(outcome, reason, suggestion id) for one group's reply; files the suggestion when the check passes."""
    if "error" in reply:
        return "error", str(reply["error"])[:1000], None
    res = reply["result"] or {}
    r = decode.check(eng[1], item["bundle"], res.get("json"), item["rows"], item["mappings"])
    if r["decision"] != "map":
        return r["decision"], r["reason"], None
    try:
        filed = suggestions.file_suggestion(
            eng, KIND, item["key"], proposal(item["key"], r["targets"]), rationale=r["reason"],
            model=res.get("model") or MODEL, filed_by=FILED_BY, prompt=decode.PROMPT)
    except HTTPException as exc:
        d = exc.detail
        return "refused", (d.get("message") if isinstance(d, dict) else str(d))[:1000], None
    return "filed", r["reason"], filed["id"]


def run(eng, *, trigger: str = "schedule", limit: int = 200, min_vehicles: int = 2, gpu: GpuClient | None = None,
        replies_path: str | None = None, export_path: str | None = None, dry_run: bool = False) -> dict:
    ji, pi = eng
    with Session(ji) as s:
        items = gather(s, pi, due_groups(s, MODEL, decode.PROMPT, min_vehicles, limit))
    if export_path:
        with open(export_path, "w") as f:
            for it in items:
                f.write(json.dumps({"id": suggestions.group_ref(it["key"]), "key": it["key"].model_dump(),
                                    "bundle": it["bundle"], "input": it["input"]}) + "\n")
        return {"exported": len(items)}
    run_row = None
    if not dry_run:
        with Session(ji) as s:
            run_row = SuggesterRun(trigger=trigger, started_at=_now(), status="running")
            s.add(run_row)
            s.commit()
            run_id = run_row.id
    counts: Counter = Counter()
    try:
        # A group with no candidates can only be "unsure": don't spend a model call on it.
        ask = [it for it in items if it["bundle"]["candidates"]]
        if replies_path:
            by_id = {json.loads(line)["id"]: json.loads(line) for line in open(replies_path)}
            answers = [by_id.get(suggestions.group_ref(it["key"]), {"error": "no reply in the file"}) for it in ask]
        else:
            answers = (gpu or GpuClient.from_env()).run(MODEL, [it["input"] for it in ask]) if ask else []
        replies = {id(it): a for it, a in zip(ask, answers)}
        for it in items:
            reply = replies.get(id(it))
            if reply is None:
                outcome, reason, sid = "unsure", "no catalogue candidates with a similar name", None
            elif dry_run:
                r = decode.check(pi, it["bundle"], (reply.get("result") or {}).get("json"), it["rows"], it["mappings"])
                outcome, reason, sid = r["decision"], r["reason"] + (f' -> {r["targets"]}' if r.get("targets") else ""), None
            else:
                outcome, reason, sid = decide(eng, it, reply)
            counts[outcome] += 1
            if dry_run:
                print(f'{outcome:8} {it["vehicles"]:5}  {it["key"].make} {it["key"].model} {it["key"].series or ""}: {reason}')
                continue
            with Session(ji) as s:
                s.add(SuggesterAttempt(run_id=run_id, kind=KIND, group_key=it["key"].model_dump(),
                                       group_ref=suggestions.group_ref(it["key"]), vehicles=it["vehicles"],
                                       model=MODEL, prompt=decode.PROMPT, outcome=outcome, reason=reason[:1000],
                                       reply=(reply or {}).get("result", {}).get("json") if reply else None,
                                       suggestion_id=sid, at=_now()))
                s.commit()
    except Exception as exc:
        if run_row is not None:
            with Session(ji) as s:
                r = s.get(SuggesterRun, run_id)
                r.status, r.finished_at, r.counts, r.error = "failed", _now(), dict(counts), str(exc)[:1000]
                s.commit()
        raise
    if run_row is not None:
        with Session(ji) as s:
            r = s.get(SuggesterRun, run_id)
            r.status, r.finished_at, r.counts = "done", _now(), dict(counts)
            s.commit()
    return {"groups": len(items), **counts}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--trigger", default="schedule", choices=("schedule", "manual"))
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--min-vehicles", type=int, default=2)
    ap.add_argument("--export")
    ap.add_argument("--replies")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    eng = (create_engine(os.environ["JUNKYARD_DATABASE_URL"]), create_engine(os.environ["PARTS_DATABASE_URL"]))
    print(json.dumps(run(eng, trigger=a.trigger, limit=a.limit, min_vehicles=a.min_vehicles,
                         replies_path=a.replies, export_path=a.export, dry_run=a.dry_run)), file=sys.stderr)


if __name__ == "__main__":
    main()
