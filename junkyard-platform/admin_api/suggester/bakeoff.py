"""Suggester bake-off (docs/matching-v2-design.md §3.5): replay decode mappings people made as groups, with that
mapping hidden, and score what a model would have suggested against what the person chose.

    # where the databases are (the admin pod): one case per labelled decode, as JSON lines
    python -m admin_api.suggester.bakeoff export [labels.json] > cases.jsonl
    python -m admin_api.suggester.bakeoff matched > cases-matched.jsonl
    # anywhere with a GPU: run each case's "input" (chat messages, JSON reply) through a model -> replies JSON lines
    #   {"id": ..., "result": {"text": ..., "json": {...}}}
    # anywhere: score
    python -m admin_api.suggester.bakeoff score cases.jsonl qwen3vl=replies-a.jsonl qwen3-8b=replies-b.jsonl [--half tune|test]
    # another prompt version over the same bundles (no database needed)
    python -m admin_api.suggester.bakeoff inputs cases.jsonl decode-v2 > cases-v2.jsonl

Prompts are written against the "tune" half of the cases only (a fixed split by a hash of the case id) and
judged on the "test" half, so a prompt isn't scored on the cases it was fitted to.

Labels: a mapping whose created_by doesn't start with "agent" was made by a person in the admin UI; "agent" ones
were made in an MCP session the person was running. They are scored separately. By default the labels are this
database's decode_mappings; labels.json (a list of decode_mappings rows as dicts) brings another environment's, e.g.
prod's, replayed against this database's cars and catalogue.

`matched` builds a second, easier answer key without anyone's labels: decodes the matcher already resolves (from
model + series) to catalogue models named differently from NHTSA's model, e.g. Ram + series 1500 -> "Ram 1500".
The cars' matches say which models are right; the model is shown the same bundle a fixable group would get.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict

from pipeline.car_matcher import name_key

from . import decode

OUTCOMES = ("exact", "subset", "wrong", "unsure", "refused", "invalid")
OUTCOME_HELP = {
    "exact": "picked exactly the person's targets",
    "subset": "picked some of them and nothing else (safe, incomplete)",
    "wrong": "picked a target the person didn't",
    "unsure": "said unsure",
    "refused": "the code check refused the pick (not a candidate, out of years, matches nothing)",
    "invalid": "the reply wasn't the JSON asked for",
}


def _truth_key(make: str, model: str) -> tuple[str, str]:
    return (make.strip().lower(), name_key(model))


def export(labels_path: str | None = None, out=sys.stdout) -> None:
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from types import SimpleNamespace

    from junkyard_common.models import DecodeMapping
    from pipeline.resolution_pipeline import load_mappings

    ji, pi = create_engine(os.environ["JUNKYARD_DATABASE_URL"]), create_engine(os.environ["PARTS_DATABASE_URL"])
    with Session(ji) as s:
        rows = ([SimpleNamespace(**r) for r in json.load(open(labels_path))] if labels_path
                else s.execute(select(DecodeMapping).order_by(DecodeMapping.id)).scalars().all())
        decodes: dict[tuple, list] = defaultdict(list)
        for m in rows:
            decodes[(m.make_key, m.model_key, m.series_key, m.year_from, m.year_to)].append(m)
        every = load_mappings(s)
        stats = Counter()
        for k, ms in decodes.items():
            first = ms[0]
            source = "agent" if any((m.created_by or "").startswith("agent") for m in ms) else "person"
            others = [m for m in every if (m.make_key, m.model_key, m.series_key, m.year_from, m.year_to) != k]
            cars = decode.decode_rows(s, first.nhtsa_make, first.nhtsa_model, first.nhtsa_series, first.year_from,
                                      first.year_to, unmatched_only=False)
            if not cars:
                stats["no cars"] += 1
                continue
            b = decode.bundle(pi, first.nhtsa_make, first.nhtsa_model, first.nhtsa_series, first.year_from,
                              first.year_to, cars, others)
            truth = sorted({(m.catalogue_make, m.catalogue_model) for m in ms})
            offered = {_truth_key(c["make"], c["model"]) for c in b["candidates"]}
            recall = sum(_truth_key(*t) in offered for t in truth)
            stats[f"{source}: cases"] += 1
            stats[f"{source}: every target among candidates"] += recall == len(truth)
            case = {"id": f'decode:{first.nhtsa_make}|{first.nhtsa_model}|{first.nhtsa_series or ""}|'
                          f'{first.year_from or ""}-{first.year_to or ""}',
                    "source": source, "truth": truth, "bundle": b,
                    "input": {"messages": decode.messages(b), "json": True, "max_new_tokens": decode.MAX_NEW_TOKENS}}
            out.write(json.dumps(case) + "\n")
    print(json.dumps(dict(stats)), file=sys.stderr)


MIN_MATCHED_CARS = 10


def matched(out=sys.stdout) -> None:
    from collections import Counter as C

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from junkyard_common.models import Vehicle, VinCache
    from pipeline.pi_schema import pi_car_table, pi_make_table, pi_model_table
    from pipeline.resolution_pipeline import load_mappings

    ji, pi = create_engine(os.environ["JUNKYARD_DATABASE_URL"]), create_engine(os.environ["PARTS_DATABASE_URL"])
    with pi.connect() as conn:
        car = {i: (mk, md) for i, mk, md in conn.execute(
            select(pi_car_table.c.id, pi_make_table.c.name, pi_model_table.c.name)
            .join(pi_model_table, pi_model_table.c.id == pi_car_table.c.model_id)
            .join(pi_make_table, pi_make_table.c.id == pi_car_table.c.make_id))}
    with Session(ji) as s:
        every = load_mappings(s)
        mapped = {(m.make_key, m.model_key) for m in every}
        q = (select(VinCache.make, VinCache.model, VinCache.raw["Series"].astext, Vehicle.car_id_candidates)
             .join(VinCache, VinCache.vin == Vehicle.vin)
             .where(Vehicle.is_active.is_(True), Vehicle.car_id_method.in_(("vin_exact", "vin_candidates"))))
        decodes: dict[tuple, C] = defaultdict(C)
        for mk, md, se, cands in s.execute(q):
            for t in {car[c] for c in (cands or []) if c in car}:
                decodes[(mk, md, se or None)][t] += 1
        stats = C()
        for (mk, md, se), targets in sorted(decodes.items(), key=lambda kv: str(kv[0])):
            if (name_key(mk), name_key(md)) in mapped or all(name_key(m) == name_key(md) for _, m in targets):
                continue          # a person's mapping covers it (scored as theirs), or no renaming to find
            cars = decode.decode_rows(s, mk, md, se, None, None, unmatched_only=False)
            if len(cars) < MIN_MATCHED_CARS:
                continue
            b = decode.bundle(pi, mk, md, se, None, None, cars, every)
            truth = sorted(targets)
            offered = {_truth_key(c["make"], c["model"]) for c in b["candidates"]}
            stats["cases"] += 1
            stats["every target among candidates"] += all(_truth_key(*t) in offered for t in truth)
            case = {"id": f"matched:{mk}|{md}|{se or ''}", "source": "matcher", "truth": truth, "bundle": b,
                    "input": {"messages": decode.messages(b), "json": True, "max_new_tokens": decode.MAX_NEW_TOKENS}}
            out.write(json.dumps(case) + "\n")
    print(json.dumps(dict(stats)), file=sys.stderr)


def outcome(case: dict, reply: dict | None) -> tuple[str, list, int]:
    """Score one reply (the model's parsed JSON) against the person's targets: the outcome, the picked names, and
    how many picks the person didn't make that would match some of the cars (an extra pick that matches none of
    them never changes a match)."""
    r = decode.check(None, case["bundle"], reply)
    if r["decision"] != "map":
        return r["decision"], [], 0
    picked = {_truth_key(t["make"], t["model"]) for t in r["targets"]}
    truth = {_truth_key(*t) for t in case["truth"]}
    names = [t["model"] for t in r["targets"]]
    live = {_truth_key(c["make"], c["model"]) for c in case["bundle"]["candidates"] if c["wouldMatch"]}
    extra = len((picked - truth) & live)
    if picked == truth:
        return "exact", names, 0
    return ("subset" if picked < truth else "wrong"), names, extra


def baseline_top1(case: dict) -> dict:
    """No model: the best-ranked candidate in the cars' years that matches any of them."""
    for c in case["bundle"]["candidates"]:
        if c["yearsInRange"] and c["wouldMatch"]:
            return {"decision": "map", "targets": [c["model"]]}
    return {"decision": "unsure"}


def half(case_id: str) -> str:
    import hashlib
    return "tune" if hashlib.sha256(case_id.encode()).digest()[0] % 2 == 0 else "test"


def inputs(cases_path: str, prompt: str, out=sys.stdout) -> None:
    for line in open(cases_path):
        c = json.loads(line)
        c["input"]["messages"] = decode.messages(c["bundle"], prompt)
        c["prompt"] = prompt
        out.write(json.dumps(c) + "\n")


def score(cases_path: str, runs: list[str], out=sys.stdout, only: str | None = None) -> None:
    cases = [json.loads(line) for line in open(cases_path)]
    if only:
        cases = [c for c in cases if half(c["id"]) == only]
    results = {"baseline: top candidate": {c["id"]: baseline_top1(c) for c in cases}}
    for run in runs:
        name, path = run.split("=", 1)
        results[name] = {}
        for line in open(path):
            r = json.loads(line)
            res = r.get("result") or {}
            results[name][r["id"]] = res.get("json") if isinstance(res, dict) else None
    by_source = Counter(c["source"] for c in cases)
    out.write(f"{len(cases)} cases ({', '.join(f'{n} {s}' for s, n in by_source.items())})\n\n")
    out.write("| run | source | " + " | ".join(OUTCOMES) + " | extra picks that match cars |\n|---|---|"
              + "---|" * (len(OUTCOMES) + 1) + "\n")
    detail = defaultdict(dict)
    for name, replies in results.items():
        for source in sorted(by_source):
            t = Counter()
            for c in cases:
                if c["source"] != source:
                    continue
                o, picked, extra = outcome(c, replies.get(c["id"]))
                t[o] += 1
                t["extra"] += extra
                detail[c["id"]][name] = f"{o}: {', '.join(picked)}" if picked else o
            out.write(f"| {name} | {source} | " + " | ".join(str(t[o]) for o in OUTCOMES) + f" | {t['extra']} |\n")
    out.write("\n" + "\n".join(f"- {o}: {h}" for o, h in OUTCOME_HELP.items()) + "\n\n")
    for c in cases:
        out.write(f"### {c['id']} ({c['source']})\nperson: {', '.join(m for _, m in c['truth'])}\n")
        for name in results:
            out.write(f"- {name}: {detail[c['id']].get(name, 'missing')}\n")
        out.write("\n")


if __name__ == "__main__":
    if sys.argv[1:2] == ["matched"]:
        matched()
    elif sys.argv[1:2] == ["export"]:
        export(sys.argv[2] if len(sys.argv) > 2 else None)
    elif sys.argv[1:2] == ["inputs"] and len(sys.argv) == 4:
        inputs(sys.argv[2], sys.argv[3])
    elif sys.argv[1:2] == ["score"] and len(sys.argv) >= 3:
        args = sys.argv[3:]
        only = args[args.index("--half") + 1] if "--half" in args else None
        score(sys.argv[2], [a for a in args if "=" in a], only=only)
    else:
        raise SystemExit(__doc__)
