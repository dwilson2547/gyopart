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


def test_other_make_candidates_need_the_make_to_tell_names_apart():
    b = {**BUNDLE, "catalogueMake": None, "decode": {**BUNDLE["decode"], "make": "RAM", "model": "1500"},
         "candidates": [
             {"make": "Dodge", "model": "Ram 1500", "years": "1994–2023", "yearsInRange": 1, "score": 1.0, "wouldMatch": 9, "exact": 9},
             {"make": "Dodge", "model": "1500", "years": "1990–1993", "yearsInRange": 1, "score": 0.9, "wouldMatch": 1, "exact": 1},
             {"make": "Chevrolet", "model": "1500", "years": "1988–1999", "yearsInRange": 1, "score": 0.9, "wouldMatch": 1, "exact": 1}]}
    r = decode.check(None, b, {"decision": "map", "targets": ["Ram 1500"]})
    assert r["targets"] == [{"make": "Dodge", "model": "Ram 1500"}]
    assert decode.check(None, b, {"decision": "map", "targets": ["1500"]})["decision"] == "refused"   # which make?
    assert decode.check(None, b, {"decision": "map", "targets": ["Chevrolet 1500"]})["targets"][0]["make"] == "Chevrolet"
    user = decode.messages(b)[1]["content"]
    assert 'Dodge "Ram 1500"' in user and "no cars of make" in user
    assert "another brand" in decode.PROMPTS["decode-v3"] and "another brand" not in decode.PROMPTS["decode-v2"]


def test_numbers_in_the_names_must_agree():
    nc = decode.number_conflict
    assert nc({"model": "Silverado", "series": "3/4 Ton"}, "Silverado 3500 HD")
    assert nc({"model": "GMT-400", "series": "1 Ton Nominal"}, "C1500")
    assert nc({"model": "Silverado", "series": "3/4 Ton"}, "Silverado 2500 HD") is None
    assert nc({"model": "Express", "series": "1500 (1/2 Ton)"}, "Express 1500") is None
    assert nc({"model": "F-550", "series": None}, "F-350 Super Duty")
    assert nc({"model": "E-450", "series": "Econoline"}, "E-150 Econoline")
    assert nc({"model": "525iA", "series": None}, "525i") is None
    assert nc({"model": "S-Class", "series": None}, "S 550") is None          # no number in the decode
    assert nc({"model": "Ram", "series": "DR (1500)"}, "Ram 1500") is None
    assert nc({"model": "GMT-400", "series": "1/2 Ton Nominal"}, "C1500") is None    # a platform code, not a model


def test_gpu_client_waits_for_the_batch_and_keeps_order():
    import httpx
    from admin_api.suggester.gpu import GpuClient, GpuUnavailable
    polls = []

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.headers["authorization"] == "Bearer t"
        if req.method == "POST":
            body = __import__("json").loads(req.content)
            assert body["model"] == "qwen3vl" and len(body["inputs"]) == 2
            return httpx.Response(202, json={"batch_id": "b1", "job_ids": ["j1", "j2"]})
        polls.append(1)
        done = len(polls) > 1
        return httpx.Response(200, json={"complete": done, "jobs": [
            {"status": "done" if done else "running", "result": {"json": {"decision": "unsure"}}, "error": None},
            {"status": "failed" if done else "queued", "result": None, "error": "boom"}]})

    c = GpuClient("http://q", "t", transport=httpx.MockTransport(handler))
    out = c.run("qwen3vl", [{"messages": []}, {"messages": []}], poll_seconds=0)
    assert out == [{"result": {"json": {"decision": "unsure"}}}, {"error": "boom"}] and len(polls) == 2
    down = GpuClient("http://q", "t", transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    import pytest
    with pytest.raises(GpuUnavailable):
        down.run("qwen3vl", [{"messages": []}])


def test_suggested_mapping_covers_the_groups_decode_for_all_years():
    from admin_api.suggester.run import proposal
    from admin_api.api.discrepancies import GroupKey
    p = proposal(GroupKey(kind="decode", make="RAM", model="1500", series=""), [{"make": "Dodge", "model": "Ram 1500"}])
    assert p == {"make": "RAM", "model": "1500", "series": None, "year_from": None, "year_to": None,
                 "targets": [{"make": "Dodge", "model": "Ram 1500"}]}
