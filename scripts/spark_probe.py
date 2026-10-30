"""Probe Muse Spark on the three things Kayé relies on: tool calling, notebook reading, mobile money.

Usage: uv run python -m scripts.spark_probe [model] [reasoning_effort]   (default muse-spark-1.3)
Prints parsed results, latency and cost per call.
"""

import asyncio
import json
import sys
import time
from pathlib import Path

from pydantic import BaseModel, ValidationError

from app.agent.schemas import (
    MobileMoneyReceipt,
    NotebookPage,
    ProposePayment,
    ProposeSale,
    inline_schema,
    tool,
)
from app.config import get_settings
from app.models_client import ModelClient, image_part

IMAGES = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "images"

SYSTEM = (
    "Tu es Kayé, l'assistant comptable d'un petit commerce au Togo, sur WhatsApp. "
    "Le commerçant te parle en français familier. Quand il décrit une vente, un crédit ou un paiement, "
    "appelle l'outil correspondant avec des montants en FCFA entiers (convertis les nombres écrits en "
    "lettres : « cinq mille » = 5000). N'invente jamais un prix qui n'a pas été dit. Unités locales : "
    "tas, bol, sac, demi-sac, tine, boîte, paquet, carton."
)

UTTERANCES = [
    "J'ai vendu trois sacs de riz à Ama et elle me doit cinq mille francs.",
    "Kofi a pris 2 bidons d'huile à 6 250 chacun, il a tout payé",
    "Maman Afi vient de me donner 3000 pour sa dette",
    "vendu 5 tas de tomates à 500 et un bol de gari à 300, cash",
]

EXTRA: dict = {}  # e.g. reasoning_effort, set from the command line

TOOLS = [tool("propose_sale", ProposeSale), tool("propose_payment", ProposePayment)]
TOOL_MODELS: dict[str, type[BaseModel]] = {"propose_sale": ProposeSale, "propose_payment": ProposePayment}


def _json_format(name: str, model: type[BaseModel]) -> dict:
    return {"type": "json_schema", "json_schema": {"name": name, "schema": inline_schema(model)}}


async def probe_tools(client: ModelClient, model: str) -> float:
    total = 0.0
    for text in UTTERANCES:
        start = time.perf_counter()
        response, usage = await client.chat(
            model=model,
            messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}],
            tools=TOOLS,
            max_tokens=4000,
            **EXTRA,
        )
        total += usage.cost_usd
        elapsed = time.perf_counter() - start
        stats = f"{elapsed:.1f}s, {usage.tokens_in} in / {usage.tokens_out} out, ${usage.cost_usd:.5f}"
        print(f"\n> {text}\n  [{stats}]")
        calls = response.choices[0].message.tool_calls or []
        if not calls:
            print(f"  ✗ no tool call, text: {response.choices[0].message.content!r}")
        for call in calls:
            try:
                args = TOOL_MODELS[call.function.name].model_validate_json(call.function.arguments)
                print(f"  ✓ {call.function.name} {args.model_dump(exclude_none=True)}")
            except (KeyError, ValidationError) as exc:
                print(f"  ✗ {call.function.name} invalid: {call.function.arguments} ({exc})")
    return total


async def probe_vision(
    client: ModelClient, model: str, image: str, prompt: str, schema: type[BaseModel]
) -> float:
    path = IMAGES / image
    mime = "image/png" if path.suffix == ".png" else "image/jpeg"
    start = time.perf_counter()
    response, usage = await client.chat(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [{"type": "text", "text": prompt}, image_part(path.read_bytes(), mime)],
            }
        ],
        response_format=_json_format(schema.__name__, schema),
        max_tokens=4000,
        **EXTRA,
    )
    elapsed = time.perf_counter() - start
    print(f"\n[{image}] {elapsed:.1f}s, {usage.tokens_in} in / {usage.tokens_out} out, ${usage.cost_usd:.5f}")
    raw = response.choices[0].message.content or ""
    try:
        parsed = schema.model_validate_json(raw)
        print(json.dumps(parsed.model_dump(exclude_none=True), ensure_ascii=False, indent=1))
    except ValidationError as exc:
        print(f"  ✗ invalid JSON for {schema.__name__}: {raw[:500]} ({exc})")
    return usage.cost_usd


async def main(model: str) -> None:
    client = ModelClient(get_settings())
    try:
        print(f"=== tool calling ({model}) ===")
        cost = await probe_tools(client, model)
        print(f"\n=== vision ({model}) ===")
        cost += await probe_vision(
            client,
            model,
            "notebook_page.jpg",
            "Photo d'une page du cahier de crédits d'un commerçant. Extrais chaque ligne de dette encore due "
            "(ignore les lignes marquées payé). Montants en FCFA entiers.",
            NotebookPage,
        )
        cost += await probe_vision(
            client,
            model,
            "tmoney_sms.png",
            "Capture d'un SMS de paiement mobile money reçu par un commerçant au Togo. Extrais le paiement.",
            MobileMoneyReceipt,
        )
        print(f"\nTOTAL ${cost:.5f}")
    finally:
        await client.aclose()


if __name__ == "__main__":
    if len(sys.argv) > 2:
        EXTRA["reasoning_effort"] = sys.argv[2]
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "muse-spark-1.3"))
