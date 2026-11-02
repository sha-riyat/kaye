"""Turns a ledger entry into the receipt image the merchant forwards to the customer.

The HTML templates in app/documents/templates are the single source of truth (they also feed the
design canvas). A headless Chromium prints them to a PNG at 1080 px wide.
"""

import asyncio
import base64
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from app.db.models import Entry, Shop
from app.documents.render import render

ASSETS = Path(__file__).resolve().parent.parent / "assets" / "brand"
CHROMIUM = ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome", "msedge")
# Windows installs are rarely on PATH (local runs only: production is Debian on Modal)
WINDOWS_BROWSERS = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)


class RenderError(Exception):
    pass


def _pretty_phone(wa_id: str | None) -> str:
    """22890000001 -> +228 90 00 00 01 (Togo); other countries are shown as received."""
    if not wa_id:
        return ""
    if wa_id.startswith("228") and len(wa_id) == 11:
        local = wa_id[3:]
        return "+228 " + " ".join(local[i : i + 2] for i in range(0, 8, 2))
    return f"+{wa_id}"


def shop_card(shop: Shop, owner_phone: str | None, logo: bytes | None = None, logo_mime: str = "image/png") -> dict:
    """The header block of every document: name, initial, contact, optional uploaded logo."""
    logo_url = f"data:{logo_mime};base64,{base64.b64encode(logo).decode()}" if logo else None
    words = [w for w in shop.name.split() if w.lower() not in {"chez", "boutique", "ets", "etablissements"}]
    initial = (words[0] if words else shop.name or "K")[0].upper()
    return {
        "name": shop.name,
        "activity": "",
        "address": "",
        "phone": _pretty_phone(owner_phone),
        "initial": initial,
        "logo_url": logo_url,
    }


def _detail(line: dict) -> str:
    from app.agent.actions import plural

    unit = line.get("unit")
    return f"{line['quantity']} {plural(unit, line['quantity'])}" if unit else f"{line['quantity']}"


def receipt_data(shop: dict, entry: Entry, number: int, customer: str, when: datetime) -> dict:
    lines = [{**ln, "detail": _detail(ln)} for ln in entry.lines]
    due = entry.debt_delta
    return {
        "shop": shop,
        "number": f"{number:04d}",
        "date": f"{when:%d/%m/%Y}",
        "time": f"{when:%H:%M}",
        "date_long": f"{when:%d/%m/%Y}",
        "customer": customer or "Client de passage",
        "lines": lines,
        "total": entry.amount,
        "paid": entry.amount - due,
        "paid_method": "mobile money" if entry.source == "mobile_money" else "espèces",
        "due": due,
        "code": f"KY-{number:04d}-{entry.id:X}",
    }


DAYS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
MONTHS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
          "novembre", "décembre")  # fmt: skip
SUMMARY_ROWS = 5  # debtors, supplier dues and low stock shown on the image; the text has the rest


def long_date(d: datetime) -> str:
    """vendredi 31 octobre 2026: the brand writes dates in words, not 2026-10-31."""
    return f"{DAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]} {d.year}"


def _day(d) -> str:
    return f"{d:%d/%m}" if d else ""


def summary_data(shop: dict, f, when: datetime) -> dict:
    """The daily (or weekly...) summary ticket. `f` is app.agent.actions.Figures."""
    p = f.period
    one_day = f.end - f.start <= timedelta(days=1)
    return {
        "shop": shop,
        "title": f"Bilan {f.label}",
        "date_long": long_date(f.start) if one_day else f"du {f.start:%d/%m} au {f.end - timedelta(days=1):%d/%m/%Y}",
        "time": f"{when:%H:%M}",
        "operations": p.operations,
        "sales": p.sales,
        "cashed": p.cashed,
        "credit": p.credit,
        "mobile_money": p.mobile_money,
        "repaid": p.repaid,
        "expenses": p.expenses,
        "supplier_paid": p.supplier_paid,
        "cash_in_hand": p.cash_in_hand,
        "debtors": [
            {"name": d.contact.name, "due": d.balance, "since": _day(d.oldest_credit_at)}
            for d in f.debtors[:SUMMARY_ROWS]
        ],
        "more_debtors": max(len(f.debtors) - SUMMARY_ROWS, 0),
        "outstanding": f.owed,
        "supplier_dues": [
            {"name": s.contact.name, "due": s.balance, "date": _day(s.due_date)} for s in f.supplier_dues[:SUMMARY_ROWS]
        ],
        "low_stock": [{"name": pr.name, "stock": pr.stock} for pr in f.low_stock[:SUMMARY_ROWS]],
        "days": _bars(f.days),
        # the breakdown only says something over several days, or when there are several labels
        "expense_lines": [{"label": label, "amount": amount} for label, amount in f.expenses[:SUMMARY_ROWS]]
        if f.days or len(f.expenses) > 1
        else [],
    }


BAR_PX = 150


def _bars(days: list) -> list[dict]:
    """Sales per day as bars: the busiest day and today carry their amount, today in Solaire."""
    if not days:
        return []
    top = max(v for _, v in days) or 1
    last = len(days) - 1
    return [
        {
            "label": f"{d.day}" if len(days) <= 10 or i % 5 == 0 or i == last else "",
            "h": max(round(max(v, 0) / top * BAR_PX), 2),
            "value": v,
            "show": i == last or (v == top and v > 0),
            "current": i == last,
        }
        for i, (d, v) in enumerate(days)
    ]


def summary_extra_height(data: dict) -> int:
    """Room for the optional sections; the image is cropped to the ticket, so too much is harmless."""
    rows = len(data["debtors"]) + len(data["supplier_dues"]) + len(data["low_stock"]) + len(data["expense_lines"])
    sections = sum(1 for k in ("supplier_dues", "low_stock", "expense_lines") if data[k])
    extra = rows * 50 + sections * 90 + (60 if data["expenses"] or data["supplier_paid"] else 0)
    return extra + (320 if data["days"] else 0)


def reminder_data(shop: dict, customer: str, items: list[dict], when: datetime) -> dict:
    """`items`: {label, due, date, receipt} for each debt still open, oldest first."""
    return {
        "shop": shop,
        "date": f"{when:%d/%m/%Y}",
        "customer": customer,
        "open_items": items,
        "due": sum(i["due"] for i in items),
        "pay_to": [],  # mobile money numbers are not recorded yet: the ticket says « à la boutique »
    }


def statement_data(shop: dict, customer: str, operations: list[dict], balance: int, when: datetime) -> dict:
    first = operations[0]["date"] if operations else f"{when:%d/%m}"
    return {
        "shop": shop,
        "period": f"du {first} au {when:%d/%m/%Y}",
        "customer": customer,
        "operations": operations,
        "balance": balance,
    }


def settlement_data(shop: dict, number: int, customer: str, before: int, entry: Entry, when: datetime) -> dict:
    return {
        "shop": shop,
        "number": f"{number:04d}",
        "date": f"{when:%d/%m/%Y}",
        "time": f"{when:%H:%M}",
        "customer": customer,
        "before": before,
        "amount": entry.amount,
        "method": "mobile money" if entry.source == "mobile_money" else "espèces",
        "reference": entry.payment_reference or "",
        "code": f"KY-Q{number:04d}-{entry.id:X}",
    }


STOCK_DAYS_FULL = 14  # a bar is full at two weeks of sales
STOCK_DAYS_LOW = 5


def stock_data(shop: dict, products: list, sold_week: dict[str, int], key, when: datetime, low_stock: int) -> dict:
    """Each tracked product with what is left and, when it sold this week, how many days that lasts."""
    from app.agent.actions import plural

    rows = []
    for p in products:
        per_day = sold_week.get(key(p.name), 0) / 7
        days = int(p.stock / per_day) if per_day > 0 and p.stock > 0 else None
        low = p.stock <= low_stock or (days is not None and days < STOCK_DAYS_LOW)
        rows.append({
            "name": p.name,
            "stock": p.stock,
            "unit": plural(p.default_unit, p.stock) if p.default_unit else "",
            "days": days,
            "w": 100 if days is None else max(min(days, STOCK_DAYS_FULL) / STOCK_DAYS_FULL * 100, 3),
            "low": low,
        })  # fmt: skip
    rows.sort(key=lambda r: (not r["low"], r["days"] if r["days"] is not None else 999, r["name"]))
    return {
        "shop": shop,
        "date_long": long_date(when),
        "time": f"{when:%H:%M}",
        "products": rows[:20],
        "more": max(len(rows) - 20, 0),
        "low_count": sum(1 for r in rows if r["low"]),
    }


def _chromium() -> str:
    for name in CHROMIUM:
        path = shutil.which(name)
        if path:
            return path
    for path in WINDOWS_BROWSERS:
        if Path(path).exists():
            return path
    raise RenderError("no Chromium found")


async def render_png(template: str, data: dict, extra_height: int = 0) -> bytes:
    """Render a document template to a PNG of the ticket alone. `extra_height` makes room for long ones."""
    html = render(template, data, asset_base=ASSETS.as_uri())
    match = re.search(r"\.doc \{ width: 1080px; height: (\d+)px", html)
    height = (int(match.group(1)) if match else 1500) + extra_height
    if match:
        html = html.replace(match.group(0), f".doc {{ width: 1080px; height: {height}px", 1)
    html = html.replace("</head>", BARE_CSS + "</head>", 1)
    with tempfile.TemporaryDirectory() as tmp:
        page, out = Path(tmp) / "doc.html", Path(tmp) / "doc.png"
        page.write_text(html, encoding="utf-8")
        # A thread rather than asyncio subprocesses, which the selector loop used on Windows lacks
        try:
            await asyncio.to_thread(
                subprocess.run,
                [_chromium(), "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                 "--allow-file-access-from-files", f"--window-size=1080,{height}", "--virtual-time-budget=8000",
                 "--default-background-color=00000000", f"--force-device-scale-factor={SCALE}",
                 f"--screenshot={out}", page.as_uri()],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=40,
            )  # fmt: skip
        except subprocess.TimeoutExpired:
            raise RenderError("Chromium timed out") from None
        if not out.exists():
            raise RenderError("Chromium produced no image")
        return _crop_to_ticket(out.read_bytes())


# The document alone: no dark page around it, no drop shadow. Transparent outside the paper, so the
# torn edge shows the chat background, like a real ticket laid on the screen.
BARE_CSS = (
    "<style>html, body, .doc { background: transparent !important; } .ticket { filter: none !important; }</style>"
)
SCALE = 2  # 680 css px of ticket -> 1360 px image: sharp on any phone


def _crop_to_ticket(png: bytes) -> bytes:
    import io

    from PIL import Image

    image = Image.open(io.BytesIO(png)).convert("RGBA")
    box = image.getchannel("A").getbbox()
    if box:
        image = image.crop(box)
    out = io.BytesIO()
    image.save(out, "PNG", optimize=True)
    return out.getvalue()


def extra_height(line_count: int) -> int:
    """Each line beyond the three the template was drawn for adds about 70 px."""
    return max(0, line_count - 3) * 70
