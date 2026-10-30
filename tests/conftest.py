import hashlib
import hmac
import json
from pathlib import Path

import pytest

from app.config import Settings

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
    )


def load_fixture(name: str) -> bytes:
    """Fixture bytes, re-serialized compactly the way Meta sends them."""
    return json.dumps(json.loads((FIXTURES / name).read_text())).encode()


def sign(body: bytes, secret: str = APP_SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
