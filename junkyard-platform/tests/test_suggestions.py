"""Fix suggestions (matching-v2-design §3.2-3.3): the checks that need no Postgres. Filing, staleness and the
approve / reject round trips use Postgres-only SQL and were verified against the dev DB."""
import pytest
from fastapi import HTTPException

from admin_api.api.suggestions import _changes_nothing, check_fits, creator, group_ref, parse
from admin_api.api.discrepancies import GroupKey
from admin_api.mcp.oauth import AGENT_PREFIX
from junkyard_common.models import FixSuggestion

DECODE = GroupKey(kind="decode", make="MERCEDES-BENZ", model="C-Class", series="C230")
TRIM = GroupKey(kind="trim", make="HYUNDAI", model="Sonata", trim="GLS/ GLS Popular")
YARD = GroupKey(kind="yard", source="lkq", make="CHEVY", model="SILVERADO 1500")


def field_of(kind, key, proposal):
    with pytest.raises(HTTPException) as e:
        check_fits(kind, key, parse(kind, proposal))
    return e.value.detail["field"]


def test_proposals_that_fit_their_group():
    check_fits("decode_mapping", DECODE, parse("decode_mapping", {
        "make": "Mercedes-Benz", "model": "C Class", "series": None,
        "targets": [{"make": "Mercedes-Benz", "model": "C 230"}]}))   # loose name keys, and any series
    check_fits("trim_mapping", TRIM, parse("trim_mapping", {
        "make": "HYUNDAI", "model": None, "trim": "GLS/ GLS Popular", "action": "map", "trims": ["GLS"]}))
    check_fits("yard_rule", YARD, parse("yard_rule", {
        "source": None, "raw_make": "chevy", "raw_model": "Silverado 1500", "make": "Chevrolet"}))
    check_fits("ignore_group", YARD, parse("ignore_group", {}))


def test_proposals_for_another_group_are_refused():
    assert field_of("decode_mapping", DECODE, {"make": "MERCEDES-BENZ", "model": "E-Class",
                                               "targets": [{"make": "Mercedes-Benz", "model": "E 320"}]}) == "proposal.model"
    assert field_of("decode_mapping", DECODE, {"make": "MERCEDES-BENZ", "model": "C-Class", "series": "C320",
                                               "targets": [{"make": "Mercedes-Benz", "model": "C 320"}]}) == "proposal.series"
    assert field_of("trim_mapping", TRIM, {"make": "HYUNDAI", "model": "Elantra", "trim": "GLS/ GLS Popular",
                                           "action": "noise"}) == "proposal.model"
    assert field_of("yard_rule", YARD, {"source": "pyp", "raw_make": "CHEVY", "raw_model": "SILVERADO 1500",
                                        "make": "Chevrolet"}) == "proposal.source"
    assert field_of("trim_mapping", DECODE, {"make": "MERCEDES-BENZ", "trim": "x", "action": "noise"}) == "kind"
    assert field_of("ignore_group", TRIM, {}) == "kind"   # trim text is settled as noise, not ignored


def test_bad_proposal_is_a_field_error():
    with pytest.raises(HTTPException) as e:
        parse("decode_mapping", {"make": "X", "model": "Y", "targets": []})
    assert e.value.detail["field"] == "proposal.targets"


def test_previews_that_do_nothing_are_not_filed():
    assert _changes_nothing("decode_mapping", {"vehicles": 0, "wouldMatch": 0})
    assert _changes_nothing("yard_rule", {"vehicles": 12, "wouldMatch": 0})
    assert _changes_nothing("trim_mapping", {"vehicles": 40, "exact": 30, "narrower": 30, "wider": 2})
    assert _changes_nothing("trim_mapping", {"vehicles": 40, "exact": 30, "narrower": 30, "wider": 0}) is None
    assert _changes_nothing("ignore_group", {"vehicles": 3}) is None


def test_group_ref_is_stable_and_distinct():
    assert group_ref(DECODE) == group_ref(GroupKey(**DECODE.model_dump()))
    assert group_ref(DECODE) != group_ref(GroupKey(kind="decode", make="MERCEDES-BENZ", model="C-Class"))


def test_an_approved_fix_is_the_users_not_the_agents():
    s = FixSuggestion(model="Claude Code")
    assert creator(s, "dan@example.com", edited=False) == "agent-suggested:Claude Code (approved by dan@example.com)"
    assert "edited by" in creator(s, "dan@example.com", edited=True)
    assert not creator(s, "u", edited=False).startswith(AGENT_PREFIX)   # so MCP delete tools can't remove it
