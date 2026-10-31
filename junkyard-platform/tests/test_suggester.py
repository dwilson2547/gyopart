"""Suggester decode check and bake-off scoring (admin_api/suggester): the parts that need no database. Bundles are
built against the dev databases (verified there)."""
from admin_api.suggester import decode
from admin_api.suggester.bakeoff import baseline_top1, outcome

BUNDLE = {"decode": {"make": "MERCEDES-BENZ", "model": "C-Class", "series": None, "yearFrom": None, "yearTo": None},
          "catalogueMake": "Mercedes-Benz", "vehicles": 10, "yards": 2, "byYear": {2004: 10}, "fields": {},
          "candidates": [
              {"make": "Mercedes-Benz", "model": "C 230", "years": "1997–2007", "yearsInRange": 1, "score": 0.85, "wouldMatch": 6, "exact": 6},
              {"make": "Mercedes-Benz", "model": "C 320", "years": "2001–2005", "yearsInRange": 1, "score": 0.85, "wouldMatch": 4, "exact": 4},
              {"make": "Mercedes-Benz", "model": "C 63 AMG", "years": "2008–2015", "yearsInRange": 0, "score": 0.8, "wouldMatch": 0, "exact": 0},
              {"make": "Mercedes-Benz", "model": "CLK 320", "years": "1998–2009", "yearsInRange": 1, "score": 0.6, "wouldMatch": 4, "exact": 4}]}
CASE = {"id": "x", "source": "person", "truth": [["Mercedes-Benz", "C 230"], ["Mercedes-Benz", "C 320"]], "bundle": BUNDLE}


def test_check_takes_only_candidates_in_the_cars_years():
    r = decode.check(None, BUNDLE, {"decision": "map", "targets": ["c230", "Mercedes-Benz C 320", "C 230"], "reason": "r"})
    assert r["decision"] == "map" and [t["model"] for t in r["targets"]] == ["C 230", "C 320"]   # loose names, deduped
    assert decode.check(None, BUNDLE, {"decision": "map", "targets": ["C 999"]})["decision"] == "refused"
    assert "years" in decode.check(None, BUNDLE, {"decision": "map", "targets": ["C 63 AMG"]})["reason"]
    assert decode.check(None, BUNDLE, {"decision": "unsure", "reason": "?"})["decision"] == "unsure"
    for bad in (None, {"decision": "maybe"}, {"decision": "map", "targets": []}, {"decision": "map", "targets": "C 230"}):
        assert decode.check(None, BUNDLE, bad)["decision"] == "invalid"


def test_outcomes_against_the_persons_targets():
    assert outcome(CASE, {"decision": "map", "targets": ["C 320", "C 230"]})[0] == "exact"
    assert outcome(CASE, {"decision": "map", "targets": ["C 230"]})[0] == "subset"
    o, _, extra = outcome(CASE, {"decision": "map", "targets": ["C 230", "CLK 320"]})
    assert (o, extra) == ("wrong", 1)                         # CLK 320 matches cars the person didn't map to it
    assert outcome(CASE, None)[0] == "invalid"


def test_baseline_takes_the_best_ranked_live_candidate():
    assert baseline_top1(CASE)["targets"] == ["C 230"]


def test_messages_name_every_candidate_and_the_reply_shape():
    sys_msg, user = decode.messages(BUNDLE)
    assert sys_msg["role"] == "system" and '"decision"' in sys_msg["content"]
    assert all(f'"{c["model"]}"' in user["content"] for c in BUNDLE["candidates"])
    assert decode.spans([2001, 2002, 2003, 2007]) == "2001–2003, 2007"


def test_every_prompt_version_renders():
    for version in decode.PROMPTS:
        assert decode.messages(BUNDLE, version)[0]["content"] == decode.PROMPTS[version]
    assert decode.PROMPT in decode.PROMPTS
