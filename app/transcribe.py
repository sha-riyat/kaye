"""Voice notes -> text with Muse Voice Transcribe (`POST /v1/asr/transcribe`).

The endpoint only accepts RIFF/WAV, mono 16-bit PCM at 16 or 24 kHz, so WhatsApp voice notes
(OGG/Opus) are converted with ffmpeg first. Limits: 32 MB body, 10 minutes of audio.
"""

import asyncio
import json
import logging
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.config import Settings

log = logging.getLogger(__name__)

USD_PER_AUDIO_HOUR = 0.18

# Words the model would otherwise mishear: local units, currency, mobile money brands.
KEYWORDS = [
    "FCFA",
    "tas",
    "bol",
    "sac",
    "demi-sac",
    "tine",
    "boîte",
    "paquet",
    "carton",
    "T-Money",
    "Flooz",
    "Moov",
    "Yas",
]


class TranscriptionError(Exception):
    pass


@dataclass
class Transcript:
    text: str
    audio_duration_ms: int

    @property
    def cost_usd(self) -> float:
        return self.audio_duration_ms / 3_600_000 * USD_PER_AUDIO_HOUR


async def to_wav(audio: bytes) -> bytes:
    """Convert any ffmpeg-readable audio to mono 16 kHz 16-bit PCM WAV.

    Goes through temp files rather than pipes so ffmpeg can write correct RIFF sizes in the header.
    """
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp) / "in", Path(tmp) / "out.wav"
        src.write_bytes(audio)
        # A thread rather than asyncio subprocesses, which the selector loop used on Windows lacks
        try:
            proc = await asyncio.to_thread(
                subprocess.run,
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                 "-i", str(src),
                 "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "-map_metadata", "-1",
                 str(dst)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )  # fmt: skip
        except FileNotFoundError:
            raise TranscriptionError("ffmpeg not installed") from None
        if proc.returncode != 0:
            raise TranscriptionError(f"ffmpeg failed: {proc.stderr.decode(errors='replace')[:300]}")
        return dst.read_bytes()


class Transcriber:
    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._http = http or httpx.AsyncClient(timeout=60)
        self._url = f"{settings.meta_model_base_url}/asr/transcribe"

    async def aclose(self) -> None:
        await self._http.aclose()

    async def transcribe(self, audio: bytes, language: str = "French") -> Transcript:
        wav = await to_wav(audio)
        request = {
            "model": self._settings.transcribe_model,
            "audioEncoding": "WAV",
            "mode": "PUSH_TO_TALK",
            "languageBias": [language],
            "keywords": KEYWORDS,
        }
        response = await self._http.post(
            self._url,
            headers={
                "Authorization": f"Bearer {self._settings.meta_model_api_key}",
                "Accept": "application/json",
            },
            files={
                "request": (None, json.dumps(request), "application/json"),
                "audio": ("voice.wav", wav, "audio/wav"),
            },
        )
        if response.is_error:
            raise TranscriptionError(f"{response.status_code}: {response.text[:300]}")

        data = response.json()
        result = Transcript(
            text=(data.get("transcript") or "").strip(),
            audio_duration_ms=int(data.get("audioDurationMs") or 0),
        )
        log.info(
            "transcribed %d ms of audio, cost $%.5f, %d chars",
            result.audio_duration_ms,
            result.cost_usd,
            len(result.text),
        )
        return result
