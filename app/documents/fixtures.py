"""Fictitious data for designing and testing documents. Never real merchant data."""


def receipt() -> dict:
    lines = [
        {"product": "Riz parfumé", "detail": "2 sacs de 25 kg", "quantity": 2, "unit_price": 12_500},
        {"product": "Huile végétale", "detail": "1 bidon de 5 L", "quantity": 1, "unit_price": 6_500},
        {"product": "Tomates", "detail": "3 tas", "quantity": 3, "unit_price": 500},
    ]
    for line in lines:
        line["total"] = line["quantity"] * line["unit_price"]
    total = sum(line["total"] for line in lines)
    paid = 25_000
    return {
        "shop": {
            "name": "Chez Afi",
            "activity": "Alimentation générale",
            "address": "Grand Marché, Lomé",
            "phone": "+228 90 00 00 01",
            "initial": "A",
        },
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


FIXTURES = {"recu": receipt}
