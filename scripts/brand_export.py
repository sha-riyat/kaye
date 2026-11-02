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
  <div class="tag">{tag}</div>
  <div class="sub">{sub}</div>
</div>
<div class="right">{symbol}
  <span class="chip" style="left:-46px;top:70px;background:{cauri};color:{nuit}">{c1}</span>
  <span class="chip" style="right:-30px;top:200px;background:#17705F;color:#FFFDF8">{c2}</span>
  <span class="chip" style="left:-20px;bottom:70px;background:#B84A1E;color:#FFFDF8">{c3}</span>
</div>
<div class="kente"></div>
</div></body></html>"""


BANNER_TEXT = {
    "en": {"tag": "Parle. Kayé note.<br><small style='font-size:26px;opacity:.75'>Speak. Kayé takes note.</small>",
           "sub": "The shop assistant of West African merchants, entirely inside WhatsApp: sales, credit, stock, receipts.",
           "c1": "Oui, noter · Yes", "c2": "Paid 25 000", "c3": "Still due 8 000"},
    "fr": {"tag": "Parle. Kayé note.",
           "sub": "L'assistant de boutique des commerçants d'Afrique de l'Ouest, entièrement dans WhatsApp : ventes, crédits, stock, reçus.",
           "c1": "Oui, noter", "c2": "Payé 25 000", "c3": "Reste dû 8 000"},
}  # fmt: skip


def banner(lang: str) -> bytes:
    symbol = f'<svg width="300" height="300" viewBox="0 0 120 120">{symbol_paths(NUIT)}</svg>'
    wordmark = (BRAND / "wordmark-cauri.svg").read_text(encoding="utf-8")
    html = BANNER.format(fonts=FONTS, nuit=NUIT, cauri=CAURI, solaire=SOLAIRE, symbol=symbol, wordmark=wordmark,
                         kente=(BRAND / "pattern-kente.svg").as_uri(), **BANNER_TEXT[lang])  # fmt: skip
    return shot(html, 1280, 640)


FEATURES = {
    "en": [("vente", "Sales and credit"), ("vocal", "Voice notes"), ("cahier-photo", "Notebook photo"),
           ("mobile-money", "Mobile money"), ("stock", "Stock"), ("depense", "Expenses"),
           ("fournisseur", "Suppliers"), ("recu", "Receipts"), ("bilan", "Summaries"), ("relance", "Reminders")],
    "fr": [("vente", "Ventes et crédits"), ("vocal", "Vocaux"), ("cahier-photo", "Photo du cahier"),
           ("mobile-money", "Mobile money"), ("stock", "Stock"), ("depense", "Dépenses"),
           ("fournisseur", "Fournisseurs"), ("recu", "Reçus"), ("bilan", "Bilans"), ("relance", "Relances")],
}  # fmt: skip


def icons(lang: str) -> bytes:
    """The adinkra-cut icons are drawn for a Cauri ground: a strip of tiles that reads in any README theme."""
    tiles = "".join(
        f'<div class="t"><img src="{(BRAND / "icons" / f"{name}.svg").as_uri()}" alt=""><span>{label}</span></div>'
        for name, label in FEATURES[lang]
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
    ("Nuit de Lomé", NUIT, CAURI, "Fond, texte", "Ground, text"), ("Cauri", CAURI, NUIT, "Fond clair", "Light ground"),
    ("Solaire", SOLAIRE, NUIT, "Action", "Action"), ("Latérite", "#B84A1E", "#FFFDF8", "Ce qui est dû", "What is due"),
    ("Lagune", "#17705F", "#FFFDF8", "Ce qui est réglé", "What is paid"),
]  # fmt: skip


def palette(lang: str) -> bytes:
    cells = "".join(
        f'<div class="c" style="background:{hex_};color:{fg}"><small>{fr if lang == "fr" else en}</small><b>{name}</b><code>{hex_}</code></div>'
        for name, hex_, fg, fr, en in PALETTE
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


ARCH_TEXT = {
    "en": {
        "title": "How Kayé works",
        "sub": "A WhatsApp message comes in, Kayé understands it, proposes, waits for « Oui » (yes), then writes in the books.",
        "a1": ("Merchant", "voice note · photo<br>text · button tap"),
        "a2": ("WhatsApp", "Cloud API<br>a real business number"),
        "a3": ("Webhook", "Modal · FastAPI<br>signature, no duplicates,<br>answers Meta in &lt; 1 s"),
        "a4": ("Understand", "voice → transcription<br>photo → cleaned up → vision<br>text → tool calling"),
        "a5": ("Decide", "Muse Spark picks a tool;<br>the code checks names<br>and recomputes amounts"),
        "meta": ("Meta Model API", "Muse Spark 1.3 · Muse Voice Transcribe 1.0<br>SAM 3.1 · Muse Image 1.0"),
        "loop": "Nothing is written without the merchant's « Oui »",
        "c5": ("Question?", "answered at once:<br>text or ticket image<br>(summary, stock, statement)"),
        "c4": ("Proposal", "one recap with<br>Oui · Corriger · Annuler<br>(Yes · Fix · Cancel)"),
        "c3": ("« Oui »", "the merchant<br>confirms with a tap"),
        "c2": ("Ledger", "the code writes the entries;<br>a correction reverses,<br>nothing is deleted"),
        "c1": ("Documents", "receipt, quittance…<br>HTML ticket → PNG<br>with headless Chromium"),
        "reply": "reply in WhatsApp",
        "write": "operation",
        "read": "question",
        "d1": (
            "Supabase Postgres",
            "ledger, contacts, stock, pending actions,<br>cost of every model call · row level security",
        ),
        "d2": ("Cloudflare R2", "voice notes, photos,<br>receipts, logos (private)"),
        "d3": ("Modal Cron · hourly", "evening summary at each shop's hour,<br>supplier reminders the day before"),
        "k1": ("≈ $2.20", "model cost per merchant per month"),
        "k2": ("0", "writes without « Oui »"),
    },
    "fr": {
        "title": "Comment Kayé fonctionne",
        "sub": "Un message WhatsApp entre, Kayé le comprend, propose, attend le « Oui », puis écrit dans le cahier.",
        "a1": ("Commerçant", "vocal · photo<br>texte · bouton"),
        "a2": ("WhatsApp", "Cloud API<br>un vrai numéro business"),
        "a3": ("Webhook", "Modal · FastAPI<br>signature, sans doublons,<br>répond à Meta en &lt; 1 s"),
        "a4": ("Comprendre", "vocal → transcription<br>photo → nettoyée → vision<br>texte → appel d'outils"),
        "a5": ("Décider", "Muse Spark choisit un outil ;<br>le code vérifie les noms<br>et recalcule les montants"),
        "meta": ("Meta Model API", "Muse Spark 1.3 · Muse Voice Transcribe 1.0<br>SAM 3.1 · Muse Image 1.0"),
        "loop": "Rien n'est écrit sans le « Oui » du commerçant",
        "c5": ("Une question ?", "réponse immédiate :<br>texte ou ticket image<br>(bilan, stock, relevé)"),
        "c4": ("Proposition", "un seul récapitulatif<br>Oui · Corriger · Annuler"),
        "c3": ("« Oui »", "le commerçant<br>confirme d'un tap"),
        "c2": ("Cahier", "le code écrit les écritures ;<br>une correction s'inverse,<br>rien n'est effacé"),
        "c1": ("Documents", "reçu, quittance…<br>ticket HTML → PNG<br>avec Chromium"),
        "reply": "réponse dans WhatsApp",
        "write": "opération",
        "read": "question",
        "d1": (
            "Supabase Postgres",
            "cahier, clients, stock, actions en attente,<br>coût de chaque appel · sécurité par ligne",
        ),
        "d2": ("Cloudflare R2", "vocaux, photos,<br>reçus, logos (privé)"),
        "d3": (
            "Modal Cron · chaque heure",
            "bilan du soir à l'heure de la boutique,<br>rappels fournisseurs la veille",
        ),
        "k1": ("≈ 2,20 $", "de modèles par commerçant et par mois"),
        "k2": ("0", "écriture sans « Oui »"),
    },
}

ARCH_CSS = f"""
body {{ margin: 0; }}
.a {{ width: 1600px; height: 1120px; position: relative; background: {NUIT}; color: {CAURI}; font-family: Inter, sans-serif; overflow: hidden; }}
h1 {{ position: absolute; left: 80px; top: 52px; margin: 0; font-family: 'Bricolage Grotesque', sans-serif; font-size: 56px; font-weight: 700; letter-spacing: -0.035em; }}
.sub {{ position: absolute; left: 80px; top: 124px; font-size: 21px; color: #D8CEE4; }}
.box {{ position: absolute; box-sizing: border-box; border-radius: 20px; padding: 16px 18px; display: flex; flex-direction: column; gap: 6px; }}
.box b {{ font-family: 'Bricolage Grotesque', sans-serif; font-size: 25px; letter-spacing: -0.02em; }}
.box span {{ font-size: 15px; line-height: 1.4; }}
.light {{ background: {CAURI}; color: {NUIT}; }}
.light span {{ color: #4E4558; }}
.dark {{ background: #241F30; border: 1.5px solid #4A4258; }}
.dark span {{ color: #D8CEE4; }}
.hot {{ background: #241F30; border: 2px solid {SOLAIRE}; }}
.hot span {{ color: #D8CEE4; }}
.sun {{ background: {SOLAIRE}; color: {NUIT}; }}
.paid {{ background: #17705F; color: #FFFDF8; }}
.paid span {{ color: #E6F2EE; }}
.n {{ position: absolute; width: 34px; height: 34px; border-radius: 50%; background: {SOLAIRE}; color: {NUIT};
      font-family: 'Bricolage Grotesque', sans-serif; font-weight: 800; font-size: 19px; display: flex; align-items: center; justify-content: center; }}
.lbl {{ position: absolute; font-size: 14px; font-weight: 600; color: #A79FB4; text-align: center; }}
.lbl.hot {{ color: {SOLAIRE}; background: none; border: 0; }}
.band {{ position: absolute; left: 60px; top: 588px; width: 1480px; height: 236px; border-radius: 28px; border: 2px dashed #4A4258; }}
.band-t {{ position: absolute; left: 380px; top: 572px; padding: 0 12px; background: {NUIT}; color: {SOLAIRE}; font-family: 'Bricolage Grotesque', sans-serif; font-size: 22px; font-weight: 700; }}
.k b {{ font-size: 44px; color: {SOLAIRE}; }}
.kente {{ position: absolute; left: 0; right: 0; bottom: 0; height: 26px; background: url("{(BRAND / "pattern-kente.svg").as_uri()}") 0 -120px / 700px auto; }}
"""


def _box(cls: str, x: int, y: int, w: int, h: int, text: tuple[str, str], number: int | None = None) -> str:
    title, body = text
    badge = f'<div class="n" style="left:{x - 14}px;top:{y - 14}px">{number}</div>' if number else ""
    return f'<div class="box {cls}" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px"><b>{title}</b><span>{body}</span></div>{badge}'


def architecture(lang: str) -> bytes:
    t = ARCH_TEXT[lang]
    W, H, ROW_A, ROW_C, ROW_D = 250, 150, 200, 630, 870
    xs = [80, 370, 660, 950, 1240]
    boxes = [
        _box("light", xs[0], ROW_A, W, H, t["a1"], 1),
        _box("light", xs[1], ROW_A, W, H, t["a2"], 2),
        _box("dark", xs[2], ROW_A, W, H, t["a3"], 3),
        _box("hot", xs[3], ROW_A, W, H, t["a4"], 4),
        _box("hot", xs[4], ROW_A, W + 30, H, t["a5"], 5),
        _box("sun", xs[3] - 60, 410, 370, 110, t["meta"]),
        _box("dark", xs[4], ROW_C, W + 30, 170, t["c5"]),
        _box("hot", xs[3], ROW_C, W, 170, t["c4"], 6),
        _box("sun", xs[2], ROW_C, W, 170, t["c3"], 7),
        _box("paid", xs[1], ROW_C, W, 170, t["c2"], 8),
        _box("light", xs[0], ROW_C, W, 170, t["c1"], 9),
        _box("dark", 80, ROW_D, 470, 120, t["d1"]),
        _box("dark", 580, ROW_D, 330, 120, t["d2"]),
        _box("dark", 940, ROW_D, 380, 120, t["d3"]),
    ]
    k1, k2 = t["k1"], t["k2"]
    keys = (
        f'<div style="position:absolute;left:1350px;top:{ROW_D - 4}px;width:200px;display:flex;flex-direction:column;gap:14px">'
        + "".join(
            f'<div class="k" style="display:flex;flex-direction:column;gap:2px"><b style="font-family:\'Bricolage Grotesque\',sans-serif;'
            f'font-size:36px;line-height:1;color:{SOLAIRE}">{v}</b><span style="font-size:14px;color:#D8CEE4">{label}</span></div>'
            for v, label in (k1, k2)
        )
        + "</div>"
    )
    mid_a = ROW_A + H // 2
    mid_c = ROW_C + 85
    grey, sun = "#A79FB4", SOLAIRE

    def arrow(d: str, color: str, dash: bool = False) -> str:
        marker = "s" if color == sun else "g"
        extra = ' stroke-dasharray="7 7"' if dash else ""
        return f'<path d="{d}" stroke="{color}" stroke-width="2.5" fill="none" marker-end="url(#{marker})"{extra}/>'

    paths = [
        arrow(f"M{xs[0] + W} {mid_a} H{xs[1] - 6}", grey),
        arrow(f"M{xs[1] + W} {mid_a} H{xs[2] - 6}", grey),
        arrow(f"M{xs[2] + W} {mid_a} H{xs[3] - 6}", grey),
        arrow(f"M{xs[3] + W} {mid_a} H{xs[4] - 6}", grey),
        # understand <-> Meta models
        arrow(f"M{xs[3] + 105} {ROW_A + H} V404", sun, dash=True),
        arrow(f"M{xs[3] + 145} 410 V{ROW_A + H + 6}", sun, dash=True),
        # decide -> question / operation
        arrow(f"M{xs[4] + 200} {ROW_A + H} V{ROW_C - 6}", grey),
        arrow(f"M{xs[4] + 60} {ROW_A + H} V560 H{xs[3] + 125} V{ROW_C - 6}", sun),  # under the Meta card
        # the loop, right to left
        arrow(f"M{xs[3]} {mid_c} H{xs[2] + W + 6}", sun),
        arrow(f"M{xs[2]} {mid_c} H{xs[1] + W + 6}", sun),
        arrow(f"M{xs[1]} {mid_c} H{xs[0] + W + 6}", sun),
        # documents back to the merchant
        arrow(f"M{xs[0] + 125} {ROW_C} V{ROW_A + H + 6}", sun),
        # storage
        arrow(f"M{xs[1] + 125} {ROW_C + 170} V{ROW_D - 6}", grey, dash=True),
        arrow(f"M{xs[0] + 125} {ROW_C + 170} V{ROW_C + 205} H700 V{ROW_D - 6}", grey, dash=True),
    ]
    labels = (
        f'<div class="lbl hot" style="left:{xs[0] + 135}px;top:{ROW_A + H + 150}px;width:150px;text-align:left">← {t["reply"]}</div>'
        f'<div class="lbl" style="left:{xs[4] + 210}px;top:{ROW_A + H + 110}px;width:110px;text-align:left">{t["read"]}</div>'
        f'<div class="lbl hot" style="left:{xs[4] + 70}px;top:{ROW_A + H + 150}px;width:120px;text-align:left">{t["write"]}</div>'
    )
    svg = (
        '<svg width="1600" height="1120" style="position:absolute;left:0;top:0" aria-hidden="true"><defs>'
        f'<marker id="g" markerWidth="10" markerHeight="10" refX="7" refY="5" orient="auto"><path d="M0 0 L10 5 L0 10 Z" fill="{grey}"/></marker>'
        f'<marker id="s" markerWidth="10" markerHeight="10" refX="7" refY="5" orient="auto"><path d="M0 0 L10 5 L0 10 Z" fill="{sun}"/></marker>'
        "</defs>" + "".join(paths) + "</svg>"
    )
    html = (
        f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8">{FONTS}<style>{ARCH_CSS}</style></head><body>'
        f'<div class="a"><h1>{t["title"]}</h1><div class="sub">{t["sub"]}</div>'
        f'<div class="band"></div><div class="band-t">{t["loop"]}</div>'
        f'{svg}{"".join(boxes)}{keys}{labels}<div class="kente"></div></div></body></html>'
    )
    return shot(html, 1600, 1120)


def main() -> None:
    for name in ("lockup-night.svg", "lockup-cauri.svg"):
        fix_lockup(BRAND / name)
    DOCS.mkdir(parents=True, exist_ok=True)
    for name, ground, ink in (("solaire", SOLAIRE, NUIT), ("night", NUIT, CAURI)):
        svg = profile_svg(ground, ink, 0.66)
        (BRAND / f"profile-{name}.svg").write_text(svg, encoding="utf-8")
        (BRAND / f"profile-{name}-640.png").write_bytes(png_of(svg, 640))
        (BRAND / f"profile-{name}-2048.png").write_bytes(png_of(svg, 2048))
    lockup = (
        (BRAND / "lockup-night.svg")
        .read_text(encoding="utf-8")
        .replace("<svg ", '<svg style="width:900px;height:auto;display:block" ', 1)
    )
    logo = f'<html><body style="margin:0;background:{CAURI};display:flex;align-items:center;justify-content:center;height:420px">{lockup}</body></html>'
    (DOCS / "logo.png").write_bytes(shot(logo, 1280, 420))
    (DOCS / "documents.png").write_bytes(documents())
    for lang in ("en", "fr"):
        (DOCS / f"banner-{lang}.png").write_bytes(banner(lang))
        (DOCS / f"features-{lang}.png").write_bytes(icons(lang))
        (DOCS / f"palette-{lang}.png").write_bytes(palette(lang))
        (DOCS / f"architecture-{lang}.png").write_bytes(architecture(lang))
    print(
        "wrote lockups, profiles (640, 2048) and docs/img/ (logo, documents, banner/features/palette/architecture in en and fr)"
    )


if __name__ == "__main__":
    main()
