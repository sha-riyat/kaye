"""Transcribe a local audio file with Muse Voice Transcribe, using META_MODEL_API_KEY from .env.

Usage: uv run python -m scripts.transcribe_file path/to/voice.ogg
"""

import asyncio
import sys
from pathlib import Path

from app.config import get_settings
from app.transcribe import Transcriber


async def main(path: Path) -> None:
    transcriber = Transcriber(get_settings())
    try:
        result = await transcriber.transcribe(path.read_bytes())
    finally:
        await transcriber.aclose()
    print(f"[{result.audio_duration_ms} ms, ${result.cost_usd:.5f}]")
    print(result.text)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    asyncio.run(main(Path(sys.argv[1])))
