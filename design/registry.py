"""Canvas registry: every item shown on the design canvas, kept in source.

Add, duplicate, rename or remove items here. To try another version, add a new entry with a new id
and a new readable name; keep the original. Positions are only the initial layout: the canvas
remembers where you moved things, keyed by id.
"""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Item:
    id: str  # stable, never reused
    name: str  # unique, readable, copied when the label is clicked: "Reçu · ticket"
    template: str  # file in app/documents/templates
    fixture: str  # key in app.documents.fixtures.FIXTURES
    w: int
    h: int
    x: int
    y: int


ITEMS: list[Item] = [
    Item("recu-ticket", "Reçu · ticket", "recu_ticket.html.j2", "recu", 1080, 1500, 0, 0),
    Item("recu-carte", "Reçu · carte", "recu_carte.html.j2", "recu", 1080, 1500, 1160, 0),
    Item("recu-cahier", "Reçu · cahier", "recu_cahier.html.j2", "recu", 1080, 1500, 2320, 0),
    # The ticket family, chosen for every document.
    Item("facture-ticket", "Facture · ticket", "facture.html.j2", "facture", 1080, 1700, 0, 1700),
    Item("proforma-ticket", "Pro forma · ticket", "proforma.html.j2", "proforma", 1080, 1600, 1160, 1700),
    Item("rappel-ticket", "Rappel de paiement · ticket", "rappel.html.j2", "rappel", 1080, 1550, 2320, 1700),
    Item("releve-ticket", "Relevé client · ticket", "releve.html.j2", "releve", 1080, 1650, 3480, 1700),
    Item("quittance-ticket", "Quittance · ticket", "quittance.html.j2", "quittance", 1080, 1450, 4640, 1700),
    Item("bilan-ticket", "Bilan du jour · ticket", "bilan.html.j2", "bilan", 1080, 1750, 5800, 1700),
    Item("bilan-semaine", "Bilan de la semaine · ticket", "bilan.html.j2", "bilan_semaine", 1080, 2300, 6960, 1700),
    Item("stock-ticket", "État du stock · ticket", "stock.html.j2", "stock", 1080, 1700, 8120, 1700),
]


def _check(items: list[Item]) -> None:
    ids = [i.id for i in items]
    names = [i.name for i in items]
    if len(set(ids)) != len(ids) or len(set(names)) != len(names):
        raise ValueError("registry ids and names must be unique")


_check(ITEMS)


def as_json() -> list[dict]:
    return [asdict(i) for i in ITEMS]


def get(item_id: str) -> Item | None:
    return next((i for i in ITEMS if i.id == item_id), None)
