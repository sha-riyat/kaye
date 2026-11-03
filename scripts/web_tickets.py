"""Render the ticket documents the website shows, from the same templates and fixtures as the app.

uv run python -m scripts.web_tickets        # writes web/src/assets/tickets/*.png
"""

from pathlib import Path

from app.db.engine import run
from app.documents import fixtures as fx
from app.receipts import render_png

OUT = Path(__file__).resolve().parent.parent / "web" / "src" / "assets" / "tickets"

# The site speaks to every trade, so its tickets come from a general shop with mixed articles
# rather than the app fixtures' grocery. Amounts stay those of the app fixtures.
SHOP = {**fx.SHOP, "name": "Boutique Étoile", "activity": "Commerce général", "initial": "É"}
LOW = [{"name": "chargeurs USB-C", "stock": 3}, {"name": "mèches", "stock": 6}]


def _receipt() -> dict:
    lines = fx._lines(
        ("Pagne wax", "6 yards", 2, 9_000), ("Mèches", "2 paquets", 2, 4_500), ("Chargeur USB-C", "", 1, 6_000)
    )
    total = sum(line["total"] for line in lines)
    return {**fx.receipt(), "shop": SHOP, "lines": lines, "total": total, "due": total - 25_000}


def _stock() -> dict:
    rows = [("chargeurs USB-C", 3, "", 4), ("mèches", 6, "paquets", 3), ("pagnes wax", 24, "", 9),
            ("écouteurs", 15, "", 12), ("savon", 18, "", 6), ("piles", 40, "", None)]  # fmt: skip
    products = [
        {"name": n, "stock": s, "unit": u, "days": d, "w": 100 if d is None else min(d, 14) / 14 * 100,
         "low": s <= 3 or (d is not None and d < 5)}
        for n, s, u, d in rows
    ]  # fmt: skip
    return {**fx.stock(), "shop": SHOP, "products": products, "low_count": sum(1 for p in products if p["low"])}


def _shop(make):
    return lambda: {**make(), "shop": SHOP}


FIXTURES = {
    **{k: _shop(v) for k, v in fx.FIXTURES.items()},
    "recu": _receipt,
    "stock": _stock,
    "quittance": lambda: {
        **fx.settlement(),
        "shop": SHOP,
        "method": "mobile money",
        "reference": "MM261102.0915.B07781",
    },
    "bilan": lambda: {**fx.daily_summary(), "shop": SHOP, "low_stock": LOW},
    "bilan_semaine": lambda: {**fx.weekly_summary(), "shop": SHOP, "low_stock": LOW},
}
TICKETS = {
    "recu": ("recu_ticket.html.j2", "recu"),
    "bilan": ("bilan.html.j2", "bilan"),
    "bilan-semaine": ("bilan.html.j2", "bilan_semaine"),
    "stock": ("stock.html.j2", "stock"),
    "quittance": ("quittance.html.j2", "quittance"),
    "rappel": ("rappel.html.j2", "rappel"),
    "releve": ("releve.html.j2", "releve"),
    "facture": ("facture.html.j2", "facture"),
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (template, fixture) in TICKETS.items():
        (OUT / f"{name}.png").write_bytes(run(render_png(template, FIXTURES[fixture](), 600)))
        print("wrote", name)


if __name__ == "__main__":
    main()
