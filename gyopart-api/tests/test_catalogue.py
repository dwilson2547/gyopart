from types import SimpleNamespace

from src.routers.catalogue import best_label, label_from_alt, pretty


def test_pretty():
    assert pretty("belts-and-cooling") == "Belts and Cooling"
    assert pretty("and-more") == "And More"


def test_label_from_alt():
    assert label_from_alt("Cooling Fan, Clutch & Motor for 2011 Ford F-150 #0") == "Cooling Fan, Clutch & Motor"
    assert label_from_alt("Valve - Rocker Arm (L.) for 1991 Acura Legend #1", "valve-rocker-arm-l") == \
        "Valve - Rocker Arm (L.)"
    assert label_from_alt("Aperture Panel for 2013 Ford F-150 #0", "back-panel") is None
    assert label_from_alt(None) is None


def test_best_label_skips_other_subcategories_alt():
    alts = ["Aperture Panel for 2013 Ford F-150 #0", "Back Panel for 2013 Ford F-150 #1"]
    assert best_label(alts, "back-panel") == "Back Panel"
    assert best_label([None], "back-panel") == "Back Panel"


def test_tree_groups_and_sorts(client, mock_db):
    mock_db.get.return_value = object()
    mock_db.execute.return_value.all.return_value = [
        SimpleNamespace(cid=2, cname="engine", sid=20, sname="oil-pump", n=1, alts=["Oil Pump for 2013 Ford F-150 #0"]),
        SimpleNamespace(cid=1, cname="body", sid=11, sname="cowl", n=3, alts=[None]),
        SimpleNamespace(cid=1, cname="body", sid=10, sname="back-panel", n=2, alts=["Aperture Panel for 2013 x #0"]),
    ]
    data = client.get("/v1/cars/1/tree").json()
    assert [c["label"] for c in data] == ["Body", "Engine"]
    assert [s["label"] for s in data[0]["subcategories"]] == ["Back Panel", "Cowl"]


def test_unknown_car_is_404(client, mock_db):
    mock_db.get.return_value = None
    assert client.get("/v1/cars/1/tree").status_code == 404
    assert client.get("/v1/cars/1/parts/search?q=alt").status_code == 404


def test_search_needs_two_chars(client, mock_db):
    assert client.get("/v1/cars/1/parts/search?q=a").status_code == 422


def test_search_places_hits(client, mock_db):
    mock_db.get.return_value = object()
    mock_db.execute.return_value.all.return_value = [
        SimpleNamespace(id=5, part_number="GB5Z-10346-C", title="Alternator", part_category_id=10, m="title",
                        diagram_id=7, part_index="1", category_id=10, sub_category_id=2741),
        SimpleNamespace(id=6, part_number="X", title="Alternator Fuse", part_category_id=12, m="title",
                        diagram_id=None, part_index=None, category_id=None, sub_category_id=None),
    ]
    data = client.get("/v1/cars/1/parts/search?q=alternator").json()
    assert data["truncated"] is False
    assert data["hits"][0]["sub_category_id"] == 2741
    assert data["hits"][1]["category_id"] == 12 and data["hits"][1]["diagram_id"] is None
