import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.webhook import InboundMessage, parse_messages, verify_signature
from tests.conftest import VERIFY_TOKEN, load_fixture, sign


@pytest.fixture
def dispatched() -> list[InboundMessage]:
    return []


@pytest.fixture
def client(settings, dispatched) -> TestClient:
    async def dispatch(msg: InboundMessage) -> None:
        dispatched.append(msg)

    return TestClient(create_app(dispatch=dispatch, settings=settings))


def post(client: TestClient, body: bytes, signature: str | None):
    headers = {"content-type": "application/json"}
    if signature is not None:
        headers["x-hub-signature-256"] = signature
    return client.post("/webhook", content=body, headers=headers)


# --- GET verification ---


def test_verification_returns_challenge(client):
    r = client.get(
        "/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": VERIFY_TOKEN, "hub.challenge": "1158201444"},
    )
    assert r.status_code == 200
    assert r.text == "1158201444"


def test_verification_rejects_wrong_token(client):
    r = client.get(
        "/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "x"},
    )
    assert r.status_code == 403


def test_verification_rejects_when_no_token_configured(settings, dispatched):
    settings.whatsapp_verify_token = ""

    async def dispatch(msg):
        dispatched.append(msg)

    c = TestClient(create_app(dispatch=dispatch, settings=settings))
    r = c.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "", "hub.challenge": "x"})
    assert r.status_code == 403


# --- POST receipt ---


def test_valid_text_message_is_dispatched(client, dispatched):
    body = load_fixture("text_message.json")
    r = post(client, body, sign(body))
    assert r.status_code == 200
    assert len(dispatched) == 1
    msg = dispatched[0]
    assert msg.wamid == "wamid.TEST_TEXT_0001"
    assert msg.sender == "22890000001"
    assert msg.profile_name == "Maman Ama"
    assert msg.type == "text"
    assert msg.text == "J'ai vendu 3 sacs de riz à Ama"


@pytest.mark.parametrize("signature", [None, "sha256=deadbeef", "md5=abc", sign(b"other body")])
def test_bad_signature_is_rejected(client, dispatched, signature):
    body = load_fixture("text_message.json")
    r = post(client, body, signature)
    assert r.status_code == 401
    assert dispatched == []


def test_signature_with_wrong_secret_is_rejected(client, dispatched):
    body = load_fixture("text_message.json")
    r = post(client, body, sign(body, secret="someone-else"))
    assert r.status_code == 401
    assert dispatched == []


def test_duplicate_delivery_is_dispatched_once(client, dispatched):
    body = load_fixture("text_message.json")
    for _ in range(3):
        assert post(client, body, sign(body)).status_code == 200
    assert len(dispatched) == 1


def test_status_updates_are_ignored(client, dispatched):
    body = load_fixture("status_update.json")
    assert post(client, body, sign(body)).status_code == 200
    assert dispatched == []


def test_invalid_json_with_valid_signature(client, dispatched):
    body = b"not json"
    assert post(client, body, sign(body)).status_code == 400
    assert dispatched == []


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


# --- Parsing ---


def test_parse_mixed_message_types():
    msgs = parse_messages(json.loads(load_fixture("mixed_messages.json")))
    by_type = {m.raw_type: m for m in msgs}

    audio = by_type["audio"]
    assert audio.type == "audio"
    assert audio.media_id == "MEDIA_AUDIO_1"
    assert audio.mime_type.startswith("audio/ogg")

    image = by_type["image"]
    assert image.type == "image"
    assert image.media_id == "MEDIA_IMAGE_1"
    assert image.text == "page du cahier"

    button = by_type["interactive"]
    assert button.type == "button"
    assert button.button_id == "confirm:42"
    assert button.text == "Oui"

    assert by_type["sticker"].type == "unsupported"
    assert all(m.phone_number_id == "200000000000002" for m in msgs)


def test_parse_ignores_other_objects():
    assert parse_messages({"object": "page", "entry": []}) == []


def test_verify_signature_fails_closed_without_secret():
    body = b"{}"
    assert verify_signature(body, sign(body, secret=""), "") is False
