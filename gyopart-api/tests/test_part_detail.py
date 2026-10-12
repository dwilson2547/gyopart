from types import SimpleNamespace
from unittest.mock import MagicMock

from src.routers.parts import image_sets


def test_image_sets_groups_triples_and_reads_callout():
    rows = [("l1", None), ("m1", None), ("s1", None)]
    assert [(i.large, i.medium, i.small) for i in image_sets(rows)] == [("l1", "m1", "s1")]
    refs = image_sets([(u, "Part can be found as reference #12 in illustration") for u in ("a", "b", "c")])
    assert refs[0].callout == "12"


def test_image_sets_ungrouped_when_not_triples():
    sets = image_sets([("a", None), ("b", None)])
    assert [(i.large, i.small) for i in sets] == [("a", "a"), ("b", "b")]
    assert image_sets([]) == []


def test_part_detail(client, mock_db):
    part = SimpleNamespace(id=5, part_number="GB5Z-10346-C", title="Alternator", other_names="Alternator Assembly, Alt",
                           description=None, replaces=None, positions=None, notes=None, msrp=637.64, manufacturer_id=1)
    mock_db.get.side_effect = lambda model, id_: part if id_ == 5 else SimpleNamespace(name="Ford")
    pics = MagicMock(); pics.all.return_value = [("l", None), ("m", None), ("s", None)]
    diags = MagicMock(); diags.all.return_value = [
        SimpleNamespace(id=7, url="d.png", alt_text="Alternator for 2013 Ford F-150 #0", sname="alternator",
                        part_index="1", category_id=10, sub_category_id=2741),
        SimpleNamespace(id=8, url="d.png", alt_text=None, sname="alternator", part_index="1", category_id=10,
                        sub_category_id=2741),
    ]
    count = MagicMock(); count.scalar_one.return_value = 164
    fits = MagicMock(); fits.first.return_value = (8697,)
    mock_db.execute.side_effect = [pics, diags, count, fits]
    data = client.get("/v1/parts/5/detail?car_id=8697").json()
    assert data["other_names"] == ["Alternator Assembly", "Alt"]
    assert data["manufacturer"] == "Ford"
    assert len(data["photos"]) == 1 and data["illustrations"] == []
    assert [d["diagram_id"] for d in data["diagrams"]] == [7]  # same drawing deduplicated
    assert data["diagrams"][0]["label"] == "Alternator"
    assert data["fit_count"] == 164 and data["fits_car"] is True


def test_part_detail_404(client, mock_db):
    mock_db.get.return_value = None
    assert client.get("/v1/parts/5/detail").status_code == 404


def test_lookup_needs_three_characters(client):
    assert client.get("/v1/parts/lookup?q=d-g").status_code == 422


def test_lookup_splits_exact_and_suggestions(client, mock_db):
    mock_db.execute.return_value.all.return_value = [
        SimpleNamespace(id=1, part_number="76515-SMA-004", title="Wiper", manufacturer="Honda", exact=True),
        SimpleNamespace(id=2, part_number="76515-SMA-004", title="Wiper", manufacturer="Acura", exact=True),
        SimpleNamespace(id=3, part_number="76515-SMA-0045", title="Wiper arm", manufacturer="Honda", exact=False),
    ]
    data = client.get("/v1/parts/lookup?q=76515 sma 004").json()
    assert data["q"] == "76515SMA004"
    assert [h["manufacturer"] for h in data["exact"]] == ["Honda", "Acura"]
    assert [h["id"] for h in data["suggestions"]] == [3]


def test_part_id_route_still_works(client, mock_db):
    mock_db.get.return_value = SimpleNamespace(id=5, title="Alternator", part_number="X", description=None, other_names=None)
    assert client.get("/v1/parts/5").json()["title"] == "Alternator"
