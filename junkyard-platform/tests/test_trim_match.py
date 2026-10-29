"""trims_meant: real NHTSA trim strings against the catalogue trims those vehicles' candidates had (dev, 2026-10-27)."""
import pytest

from pipeline.car_matcher import match_decoded
from pipeline.trim_match import trims_meant
from tests.test_car_matcher import SEBRING, _pi_engine

CASES = [
    # GM grade digits
    ("1LT", "LS / LT / LTZ", "LT"),
    ("2LT", "Eco / LT / LTZ", "LT"),
    ("LT-1LT", "LS / LT / LTZ", "LT"),
    ("LT (1LT)", "L / LS / LT / RS", "LT"),
    ("LS (&1LS)", "L / LS / LT", "LS"),
    ("1LS", "LS / LT / LTZ", "LS"),
    ("SLT2", "SLE / SLT", "SLT"),
    ("SLE 2", "Denali / SLE / SLT", "SLE"),
    ("SLT-2 1/2 Ton", "SL / SLE / SLT", "SLT"),
    # engine, drive and option words
    ("EX-V6", "EX / LX / SE", "EX"),
    ("EX-L-V6", "EX / EX-L / LX", "EX-L"),
    ("SEL FWD", "S / SE / SEL / Titanium", "SEL"),
    ("quattro Premium Plus", "Premium / Premium Plus / Prestige", "Premium Plus"),
    ("SEL w/ Convenience Pkg", "Limited / SE / SEL", "SEL"),
    ("GLS (Middle grade)", "GLS / Limited", "GLS"),
    ("LE (X Grade) ASA44L/ASA42L/AVA44L", "LE / Limited / SE / XLE", "LE"),
    # exact names, including ones with a slash, and tokens the catalogue writes with a digit
    ("T5 Inscription", "T5 Inscription / T5 Momentum", "T5 Inscription"),
    ("X/C", "2.4T / AWD / Base / T5 / X/C", "X/C"),
    ("SR5", "SR / SR5 / TRD Pro", "SR5"),
    # lists narrow to their members when every member is in the catalogue
    ("L/LE/SE/XLE/XSE", "Hybrid / L / LE / SE / XLE / XSE", "L / LE / SE / XLE / XSE"),
    ("LX, S, X-Line", "EX / GT-Line / LX / S / X-Line", "LX / S / X-Line"),
    ("SR5/TRD Pro", "SR / SR5 / TRD Pro", "SR5 / TRD Pro"),
    # ...and say nothing when any member isn't (the vehicle may be that one)
    ("Standard / Turbo / R-Spec / Rally Edition", "Base / Rally Edition / Turbo / Turbo R-Spec", None),
    ("Sport, SXT", "R/T / Sport", None),
    ("Base / LX", "EX / LX", None),
    ("Work Truck/LS/Fleet/Base 1500", "Custom / High Country / LS / LT / WT", None),
    # leftover words that might matter
    ("LX Premium", "EX / EX-L / LX / LX-P / LX-S", None),
    ("EX with leather (With RES)", "EX / EX-L / LX / Touring", None),
    ("4Motion SE w/ Technology, w/ Technology R-Line", "SE / SE R-Line / SEL / SEL R-Line", None),
    ("Platinum Inscription AWD", "Polestar / T5 Inscription / T5 Inscription Platinum", None),
    ("GT", "GT1 / GT2 / GTP", None),
    # only noise: says nothing about the trim ("" = an empty set)
    ("ZZE130L", "CE / LE / S / XRS",  ""),
    ("ACV40L/GSV40L/AHV40L", "CE / LE / SE / XLE",  ""),
    ("1500 (1/2 Ton)", "LS / LT / Z71",  ""),
    # maker-internal grades and body words: in doubt, for a trim mapping to settle
    ("Lev2 - All models", "LS / LT / LTZ", None),
    ("Middle level", "Limited / SE", None),
    ("Styleside", "XL / XLT / Lariat", None),
    ("", "LS / LT", None),
]


@pytest.mark.parametrize("text,catalogue,expected", CASES)
def test_trims_meant(text, catalogue, expected):
    want = None if expected is None else set(expected.split(" / ")) if expected else set()
    assert trims_meant(text, catalogue.split(" / ")) == want


ROWS = [(1, "LS", "2.4L L4 - Gas"), (2, "LT", "2.4L L4 - Gas"), (3, "LTZ", "2.4L L4 - Gas")]


def test_matcher_reads_gm_grades():
    m = match_decoded(dict(SEBRING, Trim="2LT"), _pi_engine(ROWS))
    assert m.candidates == [2] and m.narrowed_by == ["trim"]


def test_matcher_falls_back_to_series_when_trim_says_nothing():
    assert match_decoded(dict(SEBRING, Trim="Lev2 - All models", Series="LTZ"), _pi_engine(ROWS)).candidates == [3]


def test_yard_trim_only_when_the_decode_has_none():
    assert match_decoded(dict(SEBRING, Trim=""), _pi_engine(ROWS), yard_trim="LT").candidates == [2]
    # the decode's trim text wins, even when it says nothing usable
    assert match_decoded(dict(SEBRING, Trim="Middle level"), _pi_engine(ROWS), yard_trim="LT").candidates == [1, 2, 3]


def test_a_list_with_an_unknown_member_does_not_narrow():
    assert match_decoded(dict(SEBRING, Trim="LT, XL"), _pi_engine(ROWS)).candidates == [1, 2, 3]


# ── trim mappings and what the matcher records (matching-v2 phase 2) ─────────────────────────────

from pipeline.car_matcher import TrimMapping  # noqa: E402


def _tm(trim, action="map", trims=(), model="Sebring", year_from=None, year_to=None):
    from pipeline.car_matcher import name_key
    return TrimMapping(name_key("CHRYSLER"), name_key(model) if model else None, name_key(trim), year_from, year_to,
                       action, tuple(trims))


def test_unreadable_text_is_recorded_for_the_trims_tab():
    m = match_decoded(dict(SEBRING, Trim="Middle level"), _pi_engine(ROWS))
    assert m.candidates == [1, 2, 3] and m.trim_unread == "Middle level" and m.steps == []


def test_noise_text_is_not_recorded_as_unread():
    m = match_decoded(dict(SEBRING, Trim="ZZE130L"), _pi_engine(ROWS))
    assert m.trim_unread is None and m.steps == ["trim_noise"]


def test_nothing_is_unread_when_the_candidates_trims_dont_differ():
    rows = [(1, "LT", "2.4L L4 - Gas"), (2, "LT", "2.4L L4 - Gas")]
    assert match_decoded(dict(SEBRING, Trim="Middle level"), _pi_engine(rows)).trim_unread is None


def test_a_map_trim_mapping_narrows_and_says_so():
    m = match_decoded(dict(SEBRING, Trim="Middle level"), _pi_engine(ROWS), trim_mappings=[_tm("Middle level", trims=["LT"])])
    assert m.candidates == [2] and m.steps == ["trim_mapping"] and m.trim_unread is None


def test_a_noise_trim_mapping_moves_on_to_the_series():
    m = match_decoded(dict(SEBRING, Trim="Styleside", Series="LTZ"), _pi_engine(ROWS),
                      trim_mappings=[_tm("Styleside", "noise", model=None)])
    assert m.candidates == [3] and m.steps == ["trim", "trim_noise"]


def test_a_model_trim_mapping_beats_a_make_wide_one_and_years_limit_it():
    both = [_tm("GL", model=None, trims=["LS"]), _tm("GL", trims=["LTZ"])]
    assert match_decoded(dict(SEBRING, Trim="GL"), _pi_engine(ROWS), trim_mappings=both).candidates == [3]
    old = [_tm("GL", trims=["LS"], year_to=2005)]
    assert match_decoded(dict(SEBRING, Trim="GL"), _pi_engine(ROWS), trim_mappings=old).trim_unread == "GL"


def test_trim_mapping_simulation_counts_against_the_current_candidates():
    from admin_api.api.trims import simulate
    pi = _pi_engine(ROWS)
    rows = [(1, dict(SEBRING, Trim="Middle level"), None, [1, 2, 3]),
            (2, dict(SEBRING, Trim="Middle level", ModelYear="2010"), None, [1, 2, 3]),
            (3, dict(SEBRING, Trim="Middle level"), None, [2])]   # already exact some other way
    r = simulate(pi, rows, [], [_tm("Middle level", trims=["LT", "LTZ"])])
    assert r == {"vehicles": 3, "exact": 0, "exactBefore": 1, "narrower": 2, "unchanged": 0, "wider": 1}


def test_trim_mapping_request_checks():
    from admin_api.api.trims import TrimMappingRequest
    with pytest.raises(ValueError):
        TrimMappingRequest(make="KIA", trim="GL", action="map")
    assert TrimMappingRequest(make="KIA", trim="GL", action="noise", trims=["LX"]).trims == []
