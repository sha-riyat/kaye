"""Meta Model API client (OpenAI-compatible) with per-call cost accounting.

Costs come from the published per-million-token prices; cached input tokens are billed lower.
"""

import base64
import logging
from dataclasses import dataclass

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion

from app.config import Settings

log = logging.getLogger(__name__)

# USD per 1M tokens: (input, cached input, output)
PRICES = {
    "muse-spark-1.3": (1.25, 0.15, 4.25),
    "muse-spark-1.2": (1.25, 0.15, 4.25),
    "muse-spark-1.1": (1.25, 0.15, 4.25),
    "muse-wonder-1.0": (4.00, 0.20, 20.00),
}

DEFAULT_MODEL = "muse-spark-1.3"


@dataclass
class Usage:
    model: str
    tokens_in: int
    tokens_cached: int
    tokens_out: int

    @property
    def cost_usd(self) -> float:
        price_in, price_cached, price_out = PRICES.get(self.model, PRICES[DEFAULT_MODEL])
        uncached = self.tokens_in - self.tokens_cached
        return (uncached * price_in + self.tokens_cached * price_cached + self.tokens_out * price_out) / 1e6


def usage_of(response: ChatCompletion, model: str) -> Usage:
    u = response.usage
    cached = 0
    if u and u.prompt_tokens_details and u.prompt_tokens_details.cached_tokens:
        cached = u.prompt_tokens_details.cached_tokens
    return Usage(
        model=model,
        tokens_in=u.prompt_tokens if u else 0,
        tokens_cached=cached,
        tokens_out=u.completion_tokens if u else 0,
    )


def image_part(data: bytes, mime_type: str = "image/jpeg") -> dict:
    """Inline image content part (base64 data URL, up to 50 MB)."""
    encoded = base64.b64encode(data).decode()
    return {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded}"}}


class ModelClient:
    def __init__(self, settings: Settings) -> None:
        self.client = AsyncOpenAI(
            base_url=settings.meta_model_base_url, api_key=settings.meta_model_api_key, timeout=90
        )

    async def chat(self, *, model: str = DEFAULT_MODEL, **kwargs) -> tuple[ChatCompletion, Usage]:
        response = await self.client.chat.completions.create(model=model, **kwargs)
        usage = usage_of(response, model)
        log.info(
            "%s: %d in (%d cached), %d out, $%.5f",
            model,
            usage.tokens_in,
            usage.tokens_cached,
            usage.tokens_out,
            usage.cost_usd,
        )
        return response, usage

    async def aclose(self) -> None:
        await self.client.close()
