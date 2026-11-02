"""Export the lockups, profile pictures and README visuals from the brand sources.

    uv run python -m scripts.brand_export

Lockup: the cowrie used to stand on the baseline and rise far above the « k », so it looked high
next to the word. It now spans exactly the word's ink, from the top of the « k » to the bottom of
the « y », and the gap keeps its proportion to the symbol. (Its centre of mass sits within 0.2 % of
its box centre, so in a square it is centred by its box.)
"""

import re
import subprocess
import tempfile
from pathlib import Path

from app.receipts import _chromium

BRAND = Path(__file__).resolve().parent.parent / "assets" / "brand"
DOCS = Path(__file__).resolve().parent.parent / "docs" / "img"

NUIT, CAURI, SOLAIRE = "#14111B", "#F5E9D6", "#FF7A1F"
FONTS = (
    '<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,300..800'
    '&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">'
)


def shot(html: str, width: int, height: int, transparent: bool = False) -> bytes:
    """Screenshot an HTML page at exactly width x height CSS px."""
    with tempfile.TemporaryDirectory() as tmp:
        page, out = Path(tmp) / "page.html", Path(tmp) / "shot.png"
        page.write_text(html, encoding="utf-8")
        args = [_chromium(), "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                "--allow-file-access-from-files", f"--window-size={width},{height}", "--virtual-time-budget=8000",
                f"--screenshot={out}", page.as_uri()]  # fmt: skip
        if transparent:
            args.insert(-2, "--default-background-color=00000000")
        subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, check=False)
        return out.read_bytes()


def symbol_paths(color: str) -> str:
    """The two paths of the symbol (shell with its aperture, and the teeth), recoloured."""
    svg = (BRAND / "symbol-solaire.svg").read_text(encoding="utf-8")
    inner = re.search(r"<svg[^>]*>(.*)</svg>", svg, re.S).group(1)
    return inner.replace(SOLAIRE, color)


# The symbol's shell spans x 22-98, y 8-112 in its 120 box. In the wordmark's glyph units the « k »
# starts at x 3.87 and rises to y 30.5; the « y » descends to 115.45; the word ends at x 208.76.
SHELL = (22, 8, 98, 112)
WORD_LEFT, WORD_TOP, WORD_BOTTOM, WORD_RIGHT = 3.87, 30.5, 115.45, 208.76
WORD_Y = 4.0  # the word's vertical offset in the lockup, kept as it was
GAP_RATIO = 0.43  # space between symbol and word, as a share of the symbol's width (as before)
MARGIN = 10


def lockup_layout() -> dict:
    x0, y0, x1, y1 = SHELL
    top, bottom = WORD_TOP + WORD_Y, WORD_BOTTOM + WORD_Y
    scale = (bottom - top) / (y1 - y0)
    width = (x1 - x0) * scale
    word_x = width + width * GAP_RATIO - WORD_LEFT
    right = word_x + WORD_RIGHT
    return {
        "symbol": f"translate({-x0 * scale:.2f},{top - y0 * scale:.2f}) scale({scale:.4f})",
        "word": f"translate({word_x:.2f},{WORD_Y:.2f})",
        "viewbox": (-MARGIN, top - MARGIN, right + 2 * MARGIN, bottom - top + 2 * MARGIN),
    }


def fix_lockup(path: Path) -> None:
    """Rewrite a lockup's two transforms and its viewBox from lockup_layout()."""
    svg = path.read_text(encoding="utf-8")
    layout = lockup_layout()
    vx, vy, vw, vh = layout["viewbox"]
    svg = re.sub(r'viewBox="[^"]*" width="[^"]*" height="[^"]*"',
                 f'viewBox="{vx} {vy:.2f} {vw:.2f} {vh:.2f}" width="{vw * 4:.0f}" height="{vh * 4:.0f}"', svg, count=1)  # fmt: skip
    svg = re.sub(r'(<svg[^>]*>\s*<g) transform="[^"]*"', rf'\1 transform="{layout["symbol"]}"', svg, count=1)
    svg = re.sub(r'(<g fill="[^"]*") transform="[^"]*"', rf'\1 transform="{layout["word"]}"', svg, count=1)
    path.write_text(svg, encoding="utf-8")


def profile_svg(ground: str, ink: str, scale: float) -> str:
    """Square profile picture: the cowrie centred on a flat ground, sized for a round crop."""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="640" viewBox="0 0 120 120">'
        f'<rect width="120" height="120" fill="{ground}"/>'
        f'<g transform="translate(60 60) scale({scale}) translate(-60 -60)">{symbol_paths(ink)}</g>'
        "</svg>"
    )


def png_of(svg: str, size: int) -> bytes:
    html = f'<html><body style="margin:0">{svg.replace('width="640" height="640"', f'width="{size}" height="{size}"')}</body></html>'
    return shot(html, size, size)


BANNER = """<!doctype html><html lang="fr"><head><meta charset="utf-8">{fonts}<style>
body {{ margin: 0; }}
.b {{ width: 1280px; height: 640px; box-sizing: border-box; background: {nuit}; color: {cauri};
      font-family: Inter, sans-serif; position: relative; overflow: hidden; display: flex; }}
.kente {{ position: absolute; left: 0; right: 0; bottom: 0; height: 34px;
          background: url("{kente}") 0 -120px / 900px auto; }}
.left {{ padding: 84px 0 0 92px; display: flex; flex-direction: column; gap: 26px; width: 760px; }}
.word svg {{ display: block; width: 360px; height: auto; margin: -24px 0 -46px -16px; }}
.tag {{ font-family: 'Bricolage Grotesque', sans-serif; font-size: 44px; font-weight: 300; letter-spacing: -0.02em; line-height: 1.15; }}
.sub {{ font-size: 22px; line-height: 1.5; color: #D8CEE4; max-width: 620px; }}
.right {{ position: absolute; right: 70px; top: 60px; width: 430px; height: 480px; border-radius: 40px;
          background: {solaire}; display: flex; align-items: center; justify-content: center; }}
.chip {{ position: absolute; border-radius: 999px; padding: 12px 22px; font-size: 20px; font-weight: 600; }}
</style></head><body><div class="b">
<div class="left">
  <div class="word">{wordmark}</div>
  <div class="tag">Parle. Kayé note.</div>
  <div class="sub">L'assistant de boutique des commerçants d'Afrique de l'Ouest, entièrement dans WhatsApp : ventes, crédits, stock, reçus.</div>
</div>
<div class="right">{symbol}
  <span class="chip" style="left:-46px;top:70px;background:{cauri};color:{nuit}">Oui, noter</span>
  <span class="chip" style="right:-30px;top:200px;background:#17705F;color:#FFFDF8">Payé 25 000</span>
  <span class="chip" style="left:-20px;bottom:70px;background:#B84A1E;color:#FFFDF8">Reste dû 8 000</span>
</div>
<div class="kente"></div>
</div></body></html>"""


def banner() -> bytes:
    symbol = f'<svg width="300" height="300" viewBox="0 0 120 120">{symbol_paths(NUIT)}</svg>'
    wordmark = (BRAND / "wordmark-cauri.svg").read_text(encoding="utf-8")
    html = BANNER.format(fonts=FONTS, nuit=NUIT, cauri=CAURI, solaire=SOLAIRE, symbol=symbol, wordmark=wordmark,
                         kente=(BRAND / "pattern-kente.svg").as_uri())  # fmt: skip
    return shot(html, 1280, 640)


FEATURES = [
    ("vente", "Ventes et crédits"), ("vocal", "Vocaux"), ("cahier-photo", "Photo du cahier"),
    ("mobile-money", "Mobile money"), ("stock", "Stock"), ("depense", "Dépenses"),
    ("fournisseur", "Fournisseurs"), ("recu", "Reçus"), ("bilan", "Bilans"), ("relance", "Relances"),
]  # fmt: skip


def icons() -> bytes:
    """The adinkra-cut icons are drawn for a Cauri ground: a strip of tiles that reads in any README theme."""
    tiles = "".join(
        f'<div class="t"><img src="{(BRAND / "icons" / f"{name}.svg").as_uri()}" alt=""><span>{label}</span></div>'
        for name, label in FEATURES
    )
    html = f"""<!doctype html><html><head><meta charset="utf-8">{FONTS}<style>
body {{ margin: 0; }}
.s {{ width: 1280px; height: 300px; background: {NUIT}; display: grid; grid-template-columns: repeat(5, 1fr);
      gap: 14px; padding: 22px 28px; box-sizing: border-box; font-family: Inter, sans-serif; }}
.t {{ background: {CAURI}; border-radius: 20px; display: flex; align-items: center; gap: 14px; padding: 0 18px; }}
.t img {{ width: 64px; height: 64px; }}
.t span {{ font-family: 'Bricolage Grotesque', sans-serif; font-size: 23px; font-weight: 700; color: {NUIT}; letter-spacing: -0.02em; }}
</style></head><body><div class="s">{tiles}</div></body></html>"""
    return shot(html, 1280, 300)


PALETTE = [
    ("Nuit de Lomé", NUIT, CAURI, "Fond, texte"), ("Cauri", CAURI, NUIT, "Fond clair"),
    ("Solaire", SOLAIRE, NUIT, "Action"), ("Latérite", "#B84A1E", "#FFFDF8", "Ce qui est dû"),
    ("Lagune", "#17705F", "#FFFDF8", "Ce qui est réglé"),
]  # fmt: skip


def palette() -> bytes:
    cells = "".join(
        f'<div class="c" style="background:{hex_};color:{fg}"><small>{role}</small><b>{name}</b><code>{hex_}</code></div>'
        for name, hex_, fg, role in PALETTE
    )
    html = f"""<!doctype html><html><head><meta charset="utf-8">{FONTS}<style>
body {{ margin: 0; }}
.p {{ width: 1280px; height: 220px; display: grid; grid-template-columns: 1.4fr 1.2fr 1.2fr 1fr 1fr; font-family: Inter, sans-serif; }}
.c {{ padding: 26px 24px; display: flex; flex-direction: column; gap: 6px; }}
.c small {{ font-size: 15px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; opacity: .8; }}
.c b {{ font-family: 'Bricolage Grotesque', sans-serif; font-size: 36px; letter-spacing: -0.03em; }}
.c code {{ margin-top: auto; font-size: 19px; font-weight: 600; font-family: Inter, sans-serif; }}
</style></head><body><div class="p">{cells}</div></body></html>"""
    return shot(html, 1280, 220)


def documents() -> bytes:
    """Four of the tickets Kayé sends, side by side, from the design fixtures."""
    import io

    from PIL import Image

    from app.db.engine import run
    from app.documents.fixtures import FIXTURES
    from app.receipts import render_png

    picks = [("recu_ticket.html.j2", "recu"), ("bilan.html.j2", "bilan_semaine"),
             ("stock.html.j2", "stock"), ("quittance.html.j2", "quittance")]  # fmt: skip
    width, gap, pad = 290, 24, 40
    tickets = []
    for template, fixture in picks:
        img = Image.open(io.BytesIO(run(render_png(template, FIXTURES[fixture](), 600)))).convert("RGBA")
        tickets.append(img.resize((width, round(img.height * width / img.width)), Image.LANCZOS))
    height = max(t.height for t in tickets) + 2 * pad
    sheet = Image.new("RGBA", (len(tickets) * width + (len(tickets) - 1) * gap + 2 * pad, height), NUIT)
    for i, t in enumerate(tickets):
        sheet.alpha_composite(t, (pad + i * (width + gap), pad))
    out = io.BytesIO()
    sheet.convert("RGB").save(out, "PNG", optimize=True)
    return out.getvalue()


def main() -> None:
    for name in ("lockup-night.svg", "lockup-cauri.svg"):
        fix_lockup(BRAND / name)
    DOCS.mkdir(parents=True, exist_ok=True)
    for name, ground, ink in (("solaire", SOLAIRE, NUIT), ("night", NUIT, CAURI)):
        svg = profile_svg(ground, ink, 0.66)
        (BRAND / f"profile-{name}.svg").write_text(svg, encoding="utf-8")
        (BRAND / f"profile-{name}-640.png").write_bytes(png_of(svg, 640))
        (BRAND / f"profile-{name}-2048.png").write_bytes(png_of(svg, 2048))
    (DOCS / "banner.png").write_bytes(banner())
    lockup = (
        (BRAND / "lockup-night.svg")
        .read_text(encoding="utf-8")
        .replace("<svg ", '<svg style="width:900px;height:auto;display:block" ', 1)
    )
    logo = f'<html><body style="margin:0;background:{CAURI};display:flex;align-items:center;justify-content:center;height:420px">{lockup}</body></html>'
    (DOCS / "logo.png").write_bytes(shot(logo, 1280, 420))
    (DOCS / "features.png").write_bytes(icons())
    (DOCS / "palette.png").write_bytes(palette())
    (DOCS / "documents.png").write_bytes(documents())
    print("wrote lockups, profiles (640, 2048) and docs/img/{banner,features,palette,documents}.png")


if __name__ == "__main__":
    main()
