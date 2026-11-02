"""Render the ticket documents the website shows, from the same templates and fixtures as the app.

    uv run python -m scripts.web_tickets        # writes web/src/assets/tickets/*.png
"""

from pathlib import Path

from app.db.engine import run
from app.documents.fixtures import FIXTURES
from app.receipts import render_png

OUT = Path(__file__).resolve().parent.parent / "web" / "src" / "assets" / "tickets"
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
