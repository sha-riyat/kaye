"""Meta's media models: SAM 3.1 to count goods on a shelf photo, Muse Image to draw a shop logo."""

import base64
import logging
import re

import httpx

from app.config import Settings

log = logging.getLogger(__name__)

SAM_MODEL = "sam-3.1"
IMAGE_MODEL = "muse-image-1.0"
SAM_USD_PER_IMAGE = 0.0025
IMAGE_USD_PER_IMAGE = 0.01
MIN_CONFIDENCE = 0.7  # below this SAM's hits are slivers at the image edge or neighbouring objects

BOX = re.compile(r"<\|box;([^|]*)\|>")


class MediaModelError(Exception):
    pass


def count_boxes(sam_text: str, min_confidence: float = MIN_CONFIDENCE) -> int:
    """SAM answers one `<|box;x1=..;c=..|>` record per object found: count the confident ones."""
    count = 0
    for record in BOX.findall(sam_text):
        fields = dict(part.split("=", 1) for part in record.split(";") if "=" in part)
        if float(fields.get("c", 1)) >= min_confidence:
            count += 1
    return count


class MetaMedia:
    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None) -> None:
        self._base = settings.meta_model_base_url
        self._headers = {"Authorization": f"Bearer {settings.meta_model_api_key}"}
        self._http = http or httpx.AsyncClient(timeout=180)

    async def count(self, image: bytes, mime: str, noun: str) -> int:
        """How many `noun` (a short English noun phrase, e.g. "sack") are visible in the photo."""
        content = [
            {"type": "input_text", "text": noun},
            {"type": "input_image", "image_url": f"data:{mime};base64,{base64.b64encode(image).decode()}"},
        ]
        response = await self._http.post(
            f"{self._base}/responses",
            headers=self._headers,
            json={
                "model": SAM_MODEL,
                "input": [{"type": "message", "role": "user", "content": content}],
                "metadata": {"include_confidence": "true", "mask_encoding": "one_bit"},
            },
        )
        if response.is_error:
            raise MediaModelError(f"SAM {response.status_code}: {response.text[:300]}")
        texts = [
            part.get("text", "")
            for item in response.json().get("output", [])
            for part in item.get("content", [])
            if part.get("type") == "output_text"
        ]
        n = count_boxes("".join(texts))
        log.info("SAM counted %d × %r, $%.4f", n, noun, SAM_USD_PER_IMAGE)
        return n

    async def logos(self, prompt: str, n: int = 3) -> list[bytes]:
        response = await self._http.post(
            f"{self._base}/images/generations",
            headers=self._headers,
            json={"model": IMAGE_MODEL, "prompt": prompt, "n": n, "size": "1024x1024",
                  "response_format": "b64_json", "output_format": "png"},
        )  # fmt: skip
        if response.is_error:
            raise MediaModelError(f"Muse Image {response.status_code}: {response.text[:300]}")
        images = [base64.b64decode(item["b64_json"]) for item in response.json().get("data", [])]
        log.info("Muse Image drew %d logos, $%.2f", len(images), IMAGE_USD_PER_IMAGE * len(images))
        return images

    async def aclose(self) -> None:
        await self._http.aclose()


def logo_prompt(shop_name: str) -> str:
    return (
        f'Logo for a small neighbourhood shop in Lomé, Togo, called "{shop_name}". '
        "A single bold, simple flat symbol in two or three warm colours on a plain light background, "
        "centred, readable as a small round profile picture. No words, no letters, no mockup, no shadow."
    )
