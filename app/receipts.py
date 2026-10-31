"""Turns a ledger entry into the receipt image the merchant forwards to the customer.

The HTML templates in app/documents/templates are the single source of truth (they also feed the
design canvas). A headless Chromium prints them to a PNG at 1080 px wide.
"""

import asyncio
import base64
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from app.db.models import Entry, Shop
from app.documents.render import render

ASSETS = Path(__file__).resolve().parent.parent / "assets" / "brand"
CHROMIUM = ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable")


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
    unit = line.get("unit")
    return f"{line['quantity']} {unit}" if unit else f"{line['quantity']}"


def receipt_data(shop: dict, entry: Entry, number: int, customer: str, when: datetime) -> dict:
    lines = [{**ln, "detail": _detail(ln)} for ln in entry.lines]
    due = entry.debt_delta
    return {
        "shop": shop,
        "number": f"{number:04d}",
        "date": f"{when:%d/%m/%Y}",
        "time": f"{when:%H:%M}",
        "date_long": f"{when:%d/%m/%Y}",
        "customer": customer or "Client",
        "lines": lines,
        "total": entry.amount,
        "paid": entry.amount - due,
        "paid_method": "mobile money" if entry.source == "mobile_money" else "espèces",
        "due": due,
        "code": f"KY-{number:04d}-{entry.id:X}",
    }


def _chromium() -> str:
    for name in CHROMIUM:
        path = shutil.which(name)
        if path:
            return path
    raise RenderError("no Chromium found")


async def render_png(template: str, data: dict, extra_height: int = 0) -> bytes:
    """Render a document template to a 1080 px wide PNG. `extra_height` makes room for long documents."""
    html = render(template, data, asset_base=ASSETS.as_uri())
    match = re.search(r"\.doc \{ width: 1080px; height: (\d+)px", html)
    height = (int(match.group(1)) if match else 1500) + extra_height
    if match:
        html = html.replace(match.group(0), f".doc {{ width: 1080px; height: {height}px", 1)
    with tempfile.TemporaryDirectory() as tmp:
        page, out = Path(tmp) / "doc.html", Path(tmp) / "doc.png"
        page.write_text(html)
        proc = await asyncio.create_subprocess_exec(
            _chromium(), "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
            "--allow-file-access-from-files", f"--window-size=1080,{height}", "--virtual-time-budget=8000",
            f"--screenshot={out}", page.as_uri(),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )  # fmt: skip
        try:
            await asyncio.wait_for(proc.wait(), timeout=40)
        except TimeoutError:
            proc.kill()
            raise RenderError("Chromium timed out") from None
        if not out.exists():
            raise RenderError("Chromium produced no image")
        return out.read_bytes()


def extra_height(line_count: int) -> int:
    """Each line beyond the three the template was drawn for adds about 70 px."""
    return max(0, line_count - 3) * 70
