"""Generate fictitious test images: a handwritten notebook page and a T-Money SMS screenshot.

All names, numbers and references are invented. Usage: uv run python -m scripts.make_fixtures
"""

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tests" / "fixtures" / "images"
HAND = ROOT / "assets" / "fonts" / "Caveat.ttf"
SANS = "/usr/share/fonts/noto/NotoSans-Regular.ttf"

NOTEBOOK_LINES = [
    "28/10   Ama (marché)      3 sacs riz        reste 5 000",
    "28/10   Kofi              2 bidons huile     12 500",
    "29/10   Maman Afi         1 carton savon     4 000",
    "29/10   Yao               5 tas tomate       paye",
    "30/10   Edem              demi-sac maïs      7 500",
]


def notebook_page() -> Image.Image:
    rng = random.Random(42)
    img = Image.new("RGB", (1100, 820), (250, 246, 232))
    draw = ImageDraw.Draw(img)
    for y in range(120, 820, 60):  # ruled lines
        draw.line([(0, y), (1100, y)], fill=(170, 195, 225), width=2)
    draw.line([(90, 0), (90, 820)], fill=(225, 120, 120), width=2)  # margin

    title = ImageFont.truetype(str(HAND), 54)
    draw.text((110, 40), "Crédits clients", font=title, fill=(25, 35, 110))
    for i, line in enumerate(NOTEBOOK_LINES):
        font = ImageFont.truetype(str(HAND), rng.randint(38, 44))
        draw.text(
            (110 + rng.randint(-6, 6), 128 + i * 120 + rng.randint(-4, 4)),
            line,
            font=font,
            fill=(25, 35, 110),
        )

    img = img.rotate(2.5, expand=True, fillcolor=(60, 50, 40))  # photo slightly tilted
    return img.filter(ImageFilter.GaussianBlur(0.8))


def tmoney_sms() -> Image.Image:
    img = Image.new("RGB", (720, 900), (18, 18, 18))
    draw = ImageDraw.Draw(img)
    header = ImageFont.truetype(SANS, 34)
    body = ImageFont.truetype(SANS, 28)
    draw.text((40, 40), "TMoney", font=header, fill=(235, 235, 235))
    draw.rounded_rectangle([(30, 130), (690, 520)], radius=28, fill=(48, 48, 52))
    text = (
        "Vous avez recu 5 000 FCFA de\n"
        "AMA KOUDJO (90 00 00 01)\n"
        "le 30/10/2026 a 14:32.\n"
        "Nouveau solde: 61 250 FCFA.\n"
        "Ref: TM261030.1432.A01234\n"
        "Frais: 0 FCFA."
    )
    draw.multiline_text((60, 160), text, font=body, fill=(235, 235, 235), spacing=14)
    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    notebook_page().save(OUT / "notebook_page.jpg", quality=85)
    tmoney_sms().save(OUT / "tmoney_sms.png")
    print(f"wrote {OUT / 'notebook_page.jpg'} and {OUT / 'tmoney_sms.png'}")


if __name__ == "__main__":
    main()
