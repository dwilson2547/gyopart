from types import SimpleNamespace

from src.routers.parts import group_interchange, year_ranges


def _r(car_id, year, make, model, trim="XLT", engine="3.5L V6 - Gas"):
    return SimpleNamespace(car_id=car_id, year=year, make=make, model=model, trim=trim, engine=engine)


def test_year_ranges():
    assert year_ranges([2013, 2009, 2010, 2011, 2011]) == "2009–2011, 2013"
    assert year_ranges([2020]) == "2020"
    assert year_ranges([]) == ""


def test_group_interchange():
    out = group_interchange(5, [
        _r(1, "2013", "Ford", "F-150"), _r(2, "2013", "Ford", "F-150", trim="FX4"), _r(3, "2011", "Ford", "F-150"),
        _r(4, "2012", "Ford", "Explorer"), _r(5, "2010", "Lincoln", "MKT"), _r(6, None, "Ford", "F-150"),
    ])
    assert out.car_count == 5
    assert [m.make for m in out.makes] == ["Ford", "Lincoln"]
    ford = out.makes[0]
    assert [m.model for m in ford.models] == ["Explorer", "F-150"]
    f150 = ford.models[1]
    assert f150.year_ranges == "2011, 2013" and f150.car_count == 3
    assert [y.year for y in f150.years] == [2013, 2011]
    assert [c.trim for c in f150.years[0].cars] == ["FX4", "XLT"]


def test_interchange_404(client, mock_db):
    mock_db.get.return_value = None
    assert client.get("/v1/parts/5/interchange").status_code == 404
