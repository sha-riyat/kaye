"""Fictitious data for designing and testing documents. Never real merchant data.

The fixtures tell one coherent story at the shop "Chez Afi": Ama's statement, reminder and the
daily summary agree on what she owes.
"""

SHOP = {
    "name": "Chez Afi",
    "activity": "Alimentation générale",
    "address": "Grand Marché, Lomé",
    "phone": "+228 90 00 00 01",
    "initial": "A",
}

PAY_TO = [
    {"name": "T-Money", "number": "+228 90 00 00 01"},
    {"name": "Flooz", "number": "+228 99 00 00 01"},
]


def _lines(*rows: tuple[str, str, int, int]) -> list[dict]:
    return [{"product": p, "detail": d, "quantity": q, "unit_price": u, "total": q * u} for p, d, q, u in rows]


def receipt() -> dict:
    lines = _lines(
        ("Riz parfumé", "2 sacs de 25 kg", 2, 12_500),
        ("Huile végétale", "1 bidon de 5 L", 1, 6_500),
        ("Tomates", "3 tas", 3, 500),
    )
    total = sum(line["total"] for line in lines)
    paid = 25_000
    return {
        "shop": SHOP,
        "number": "0042",
        "date": "31/10/2026",
        "time": "14:32",
        "date_long": "31 octobre 2026",
        "customer": "Ama Koudjo",
        "lines": lines,
        "total": total,
        "paid": paid,
        "paid_method": "espèces",
        "due": total - paid,
        "code": "KY-0042-7F3A",
    }


def invoice() -> dict:
    lines = _lines(
        ("Riz parfumé", "4 sacs de 25 kg", 4, 12_500),
        ("Huile végétale", "3 bidons de 5 L", 3, 6_500),
        ("Oignons", "2 sacs", 2, 9_000),
    )
    return {
        "shop": SHOP,
        "number": "F-2026-018",
        "date": "31/10/2026",
        "due_date": "15/11/2026",
        "customer": {"name": "Maquis Le Palmier", "phone": "+228 91 00 00 02"},
        "lines": lines,
        "total": sum(line["total"] for line in lines),
        "pay_to": PAY_TO,
        "code": "KY-F018-2C9D",
    }


def proforma() -> dict:
    lines = _lines(
        ("Riz parfumé", "6 sacs de 25 kg", 6, 12_500),
        ("Huile végétale", "4 bidons de 5 L", 4, 6_500),
        ("Sucre", "2 cartons", 2, 11_000),
    )
    return {
        "shop": SHOP,
        "number": "PF-0007",
        "date": "31/10/2026",
        "valid_until": "07/11/2026",
        "customer": {"name": "Maquis Le Palmier"},
        "lines": lines,
        "total": sum(line["total"] for line in lines),
        "code": "KY-PF07-91AE",
    }


AMA_OPEN = [
    {"label": "Achat du 31/10", "due": 8_000, "date": "31/10/2026", "receipt": "0042"},
    {"label": "Reste de l'achat du 28/10", "due": 3_000, "date": "28/10/2026", "receipt": "0039"},
    {"label": "Achat du 21/10", "due": 4_000, "date": "21/10/2026", "receipt": "0035"},
]


def reminder() -> dict:
    return {
        "shop": SHOP,
        "date": "03/11/2026",
        "customer": "Ama Koudjo",
        "open_items": AMA_OPEN,
        "due": sum(i["due"] for i in AMA_OPEN),
        "pay_to": PAY_TO,
    }


def statement() -> dict:
    operations = [
        {"date": "02/10", "label": "Achat · reçu 0021", "delta": 6_500},
        {"date": "09/10", "label": "Paiement Flooz", "delta": -6_500},
        {"date": "21/10", "label": "Achat · reçu 0035", "delta": 4_000},
        {"date": "28/10", "label": "Achat · reçu 0039", "delta": 5_000},
        {"date": "29/10", "label": "Paiement espèces", "delta": -2_000},
        {"date": "31/10", "label": "Achat · reçu 0042", "delta": 8_000},
    ]
    return {
        "shop": SHOP,
        "period": "du 01/10 au 03/11/2026",
        "customer": "Ama Koudjo",
        "operations": operations,
        "balance": sum(op["delta"] for op in operations),
    }


def settlement() -> dict:
    return {
        "shop": SHOP,
        "number": "Q-0011",
        "date": "02/11/2026",
        "time": "09:15",
        "customer": "Kofi Mensah",
        "before": 12_500,
        "amount": 12_500,
        "method": "T-Money",
        "reference": "TM261102.0915.B07781",
        "code": "KY-Q011-55D0",
    }


def daily_summary() -> dict:
    debtors = [
        {"name": "Ama Koudjo", "due": sum(i["due"] for i in AMA_OPEN), "since": "21/10"},
        {"name": "Edem Agbeko", "due": 7_500, "since": "30/10"},
        {"name": "Yao Dzifa", "due": 4_000, "since": "29/10"},
    ]
    cashed, credit, repaid, expenses = 112_000, 36_500, 14_000, 5_000
    return {
        "shop": SHOP,
        "title": "Bilan du jour",
        "date_long": "vendredi 31 octobre 2026",
        "time": "20:00",
        "operations": 23,
        "sales": cashed + credit,
        "cashed": cashed,
        "credit": credit,
        "mobile_money": 28_000,
        "repaid": repaid,
        "expenses": expenses,
        "supplier_paid": 0,
        "cash_in_hand": cashed + repaid - expenses,
        "debtors": debtors,
        "more_debtors": 0,
        "outstanding": sum(d["due"] for d in debtors),
        "supplier_dues": [{"name": "Koffi", "due": 180_000, "date": "07/11"}],
        "low_stock": [{"name": "tomate concentrée", "stock": 2}, {"name": "huile 5 L", "stock": 3}],
        "days": [],
        "expense_lines": [{"label": "transport", "amount": 3_500}, {"label": "sachets", "amount": 1_500}],
    }


WEEK = [(25, 176_000), (26, 64_000), (27, 98_500), (28, 112_000), (29, 87_000), (30, 131_500), (31, 148_500)]


def weekly_summary() -> dict:
    top = max(v for _, v in WEEK)
    days = [
        {"label": str(d), "h": round(v / top * 150), "value": v, "show": v == top or i == 6, "current": i == 6}
        for i, (d, v) in enumerate(WEEK)
    ]
    sales = sum(v for _, v in WEEK)
    credit = 82_000
    return {
        **daily_summary(),
        "title": "Bilan des 7 derniers jours",
        "date_long": "du 25/10 au 31/10/2026",
        "operations": 141,
        "sales": sales,
        "cashed": sales - credit,
        "credit": credit,
        "mobile_money": 164_000,
        "repaid": 61_000,
        "expenses": 38_500,
        "cash_in_hand": sales - credit + 61_000 - 38_500,
        "days": days,
        "expense_lines": [
            {"label": "loyer", "amount": 20_000},
            {"label": "transport", "amount": 12_500},
            {"label": "sachets", "amount": 6_000},
        ],
    }


def stock() -> dict:
    rows = [
        ("tomate concentrée", 6, "boîtes", 2),
        ("huile 5 L", 3, "bidons", 4),
        ("savon", 18, "", 6),
        ("riz 25 kg", 32, "sacs", 9),
        ("sucre 1 kg", 118, "paquets", 14),
        ("piles", 40, "", None),
    ]
    products = [
        {"name": n, "stock": s, "unit": u, "days": d, "w": 100 if d is None else min(d, 14) / 14 * 100,
         "low": s <= 3 or (d is not None and d < 5)}
        for n, s, u, d in rows
    ]  # fmt: skip
    return {
        "shop": SHOP,
        "date_long": "vendredi 31 octobre 2026",
        "time": "18:40",
        "products": products,
        "more": 0,
        "low_count": sum(1 for p in products if p["low"]),
    }


FIXTURES = {
    "recu": receipt,
    "facture": invoice,
    "proforma": proforma,
    "rappel": reminder,
    "releve": statement,
    "quittance": settlement,
    "bilan": daily_summary,
    "bilan_semaine": weekly_summary,
    "stock": stock,
}
