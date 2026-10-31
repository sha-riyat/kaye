import pytest
from fastapi.testclient import TestClient

from app.documents.fixtures import FIXTURES
from app.documents.render import fcfa, render
from design import registry
from design.server import app

NNBSP = " "


def test_fcfa_groups_thousands_with_narrow_space():
    assert fcfa(33_000) == f"33{NNBSP}000"
    assert fcfa(500) == "500"
    assert fcfa(1_250_000) == f"1{NNBSP}250{NNBSP}000"


def test_receipt_fixture_amounts_are_consistent():
    r = FIXTURES["recu"]()
    assert r["total"] == sum(line["quantity"] * line["unit_price"] for line in r["lines"])
    assert r["due"] == r["total"] - r["paid"]
    assert all(isinstance(line["total"], int) for line in r["lines"])


@pytest.mark.parametrize("item", registry.ITEMS, ids=lambda i: i.id)
def test_every_registry_item_renders(item):
    data = FIXTURES[item.fixture]()
    html = render(item.template, data)
    assert data["shop"]["name"] in html
    for key in ("total", "due", "balance", "sales", "outstanding", "amount"):
        if key in data:
            assert fcfa(data[key]) in html, key
    assert "/brand/" in html


def test_story_is_consistent_across_documents():
    statement = FIXTURES["releve"]()
    reminder = FIXTURES["rappel"]()
    summary = FIXTURES["bilan"]()
    ama = next(d for d in summary["debtors"] if d["name"] == "Ama Koudjo")
    assert statement["balance"] == reminder["due"] == ama["due"]
    assert summary["sales"] == summary["cashed"] + summary["credit"]
    invoice = FIXTURES["facture"]()
    assert invoice["total"] == sum(line["total"] for line in invoice["lines"])


def test_registry_ids_and_names_unique():
    assert len({i.id for i in registry.ITEMS}) == len(registry.ITEMS)
    assert len({i.name for i in registry.ITEMS}) == len(registry.ITEMS)


def test_canvas_server_routes():
    client = TestClient(app)
    assert client.get("/").status_code == 200
    assert [i["id"] for i in client.get("/registry").json()] == [i.id for i in registry.ITEMS]
    assert client.get("/preview/recu-carte").status_code == 200
    assert client.get("/preview/does-not-exist").status_code == 404
    assert len(client.get("/version").json()["v"]) == 12
