import asyncio
import hashlib
import hmac
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app.config import Settings

if sys.platform == "win32":  # async psycopg cannot run on the default Proactor loop (see app.db.engine.run)
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

FIXTURES = Path(__file__).parent / "fixtures"
APP_SECRET = "test-app-secret"
VERIFY_TOKEN = "test-verify-token"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        whatsapp_access_token="test-token",
        whatsapp_phone_number_id="200000000000002",
        whatsapp_app_secret=APP_SECRET,
        whatsapp_verify_token=VERIFY_TOKEN,
        whatsapp_api_version="v26.0",
        meta_model_api_key="test-meta-key",
    )


@pytest.fixture(scope="session")
def voice_note_ogg(tmp_path_factory) -> bytes:
    """A 1 s OGG/Opus tone, the same container WhatsApp uses for voice notes."""
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    path = tmp_path_factory.mktemp("audio") / "voice.ogg"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-ac", "1", "-ar", "48000", "-c:a", "libopus", str(path)],
        check=True,
    )  # fmt: skip
    return path.read_bytes()


def load_fixture(name: str) -> bytes:
    """Fixture bytes, re-serialized compactly the way Meta sends them."""
    return json.dumps(json.loads((FIXTURES / name).read_text(encoding="utf-8"))).encode()


def sign(body: bytes, secret: str = APP_SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
