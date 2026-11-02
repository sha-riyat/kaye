"""Compare ways of reading handwritten notebook pages with Meta's models.

    uv run python -m scripts.handwriting_eval <folder or image> [strategy ...]

Each image may have a `<name>.txt` beside it with the true lines (one per line): the script then
prints how many characters of it each strategy got right. Strategies, cheapest first:

    spark       Muse Spark 1.3 reads the whole page, reasoning off (what Kayé does today)
    spark-low   the same with reasoning_effort=low
    spark-prep  the page cleaned up first (orientation, contrast, size), reasoning low
    spark-strips  the cleaned page cut into overlapping bands, each read on its own
    wonder      Muse Wonder 1.0 on the cleaned page

Every strategy only TRANSCRIBES (line by line, as written); interpreting the lines is a separate,
text-only step that is not measured here.
"""

import asyncio
import difflib
import io
import json
import sys
import time
from pathlib import Path

from PIL import Image

from app.config import get_settings
from app.images import prepare_for_reading
from app.models_client import ModelClient, image_part

PROMPT = (
    "Photo d'une page de cahier d'un commerçant d'Afrique de l'Ouest, écrite à la main en français. "
    "Recopie chaque ligne EXACTEMENT comme elle est écrite, de haut en bas, sans corriger, sans traduire, "
    "sans rien inventer. Garde les chiffres, les dates, les noms et les abréviations tels quels. "
    "Un mot illisible : écris [?]. Une ligne barrée : commence-la par ~~. "
    'Réponds en JSON : {"lines": ["...", "..."]}'
)
STRIP_PROMPT = (
    "Bande horizontale d'une page de cahier écrite à la main en français (d'autres bandes suivent). "
    "Recopie chaque ligne COMPLÈTE visible EXACTEMENT comme elle est écrite, sans corriger ni inventer. "
    "Ignore une ligne coupée par le haut ou le bas de la bande. Un mot illisible : [?]. "
    'Réponds en JSON : {"lines": ["...", "..."]}'
)
FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "Transcription",
        "schema": {"type": "object", "properties": {"lines": {"type": "array", "items": {"type": "string"}}},
                   "required": ["lines"]},
    },
}  # fmt: skip


def prepare(data: bytes) -> bytes:
    return prepare_for_reading(data)[0]


def strips(data: bytes, count: int = 3, overlap: float = 0.12) -> list[bytes]:
    img = Image.open(io.BytesIO(data))
    step = img.height / count
    pad = round(step * overlap)
    out = []
    for i in range(count):
        top, bottom = max(round(i * step) - pad, 0), min(round((i + 1) * step) + pad, img.height)
        buf = io.BytesIO()
        img.crop((0, top, img.width, bottom)).save(buf, "JPEG", quality=90)
        out.append(buf.getvalue())
    return out


async def read(client: ModelClient, model: str, data: bytes, prompt: str, **extra) -> tuple[list[str], float]:
    response, usage = await client.chat(
        model=model,
        messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, image_part(data, "image/jpeg")]}],
        response_format=FORMAT, **{"max_tokens": 4000, **extra},
    )  # fmt: skip
    raw = response.choices[0].message.content or "{}"
    try:
        return [ln.strip() for ln in json.loads(raw).get("lines", []) if ln.strip()], usage.cost_usd
    except json.JSONDecodeError:
        return [f"✗ not JSON: {raw[:200]}"], usage.cost_usd


async def run_strategy(client: ModelClient, name: str, data: bytes) -> tuple[list[str], float]:
    if name == "spark":
        return await read(client, "muse-spark-1.3", data, PROMPT, reasoning_effort="minimal")
    if name == "spark-low":
        return await read(client, "muse-spark-1.3", data, PROMPT, reasoning_effort="low")
    if name == "spark-prep":
        return await read(client, "muse-spark-1.3", prepare(data), PROMPT, reasoning_effort="low")
    if name == "spark-strips":
        parts = await asyncio.gather(
            *(read(client, "muse-spark-1.3", s, STRIP_PROMPT, reasoning_effort="low") for s in strips(prepare(data)))
        )
        lines: list[str] = []
        for part, _ in parts:
            lines += [ln for ln in part if ln not in lines[-4:]]  # the overlap repeats a line or two
        return lines, sum(c for _, c in parts)
    if name == "kaye":  # exactly what production does: cleaned photo, vision prompt, tools
        from datetime import UTC, datetime

        from app.agent.loop import VISION_PARAMS, VISION_TOOLS
        from app.agent.prompts import vision_prompt

        clean, mime = prepare_for_reading(data)
        content = [{"type": "text", "text": vision_prompt(datetime.now(UTC))}, image_part(clean, mime)]
        response, usage = await client.chat(
            messages=[{"role": "user", "content": content}], tools=VISION_TOOLS, tool_choice="auto", **VISION_PARAMS
        )
        lines = []
        for call in response.choices[0].message.tool_calls or []:
            args = json.loads(call.function.arguments)
            lines.append(f"[{call.function.name}] date={args.get('date')}")
            for ln in args.get("lines", []):
                flag = " ❓" if ln.get("unclear") else ""
                who = f" ({ln['customer']})" if ln.get("customer") else ""
                lines.append(f"{ln.get('product')}{who} → {ln.get('amount', ln.get('amount_owed'))}{flag}")
        return lines or [response.choices[0].message.content or "∅"], usage.cost_usd
    if name == "wonder":
        return await read(client, "muse-wonder-1.0", prepare(data), PROMPT, max_tokens=16000)
    raise SystemExit(f"unknown strategy {name}")


def _norm(lines: list[str]) -> list[str]:
    """Compare what was read, not how it was punctuated: arrows, dashes, F/Fr, spaces."""
    out = []
    for ln in lines:
        ln = ln.lower().replace("→", " ").replace("->", " ").replace("fr", "f").lstrip("-–• ")
        out.append("".join(ln.split()))
    return [ln for ln in out if ln]


def score(lines: list[str], truth: list[str]) -> float:
    """Share of the true lines read exactly (after normalising), in order."""
    read, want = _norm(lines), _norm(truth)
    matcher = difflib.SequenceMatcher(None, read, want, autojunk=False)
    return sum(b.size for b in matcher.get_matching_blocks()) / max(len(want), 1)


async def main(target: Path, names: list[str]) -> None:
    images = sorted(p for p in ([target] if target.is_file() else target.iterdir())
                    if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"))  # fmt: skip
    client = ModelClient(get_settings())
    try:
        for path in images:
            truth_file = path.with_suffix(".txt")
            truth = truth_file.read_text(encoding="utf-8").splitlines() if truth_file.exists() else None
            print(f"\n######## {path.name}")
            for name in names:
                start = time.perf_counter()
                lines, cost = await run_strategy(client, name, path.read_bytes())
                took = time.perf_counter() - start
                accuracy = f" · {score(lines, truth):.0%} des lignes exactes" if truth else ""
                print(f"\n== {name}: {took:.1f}s · ${cost:.4f}{accuracy}")
                for ln in lines:
                    print(f"   {ln}")
    finally:
        await client.aclose()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    asyncio.run(main(Path(sys.argv[1]), sys.argv[2:] or ["spark", "spark-low", "spark-prep", "spark-strips", "wonder"]))
