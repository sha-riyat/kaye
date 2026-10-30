import json

import httpx
import pytest
import respx

from app.router import UNSUPPORTED_REPLY, handle_message
from app.webhook import parse_messages
from app.whatsapp import WhatsAppClient
from tests.conftest import load_fixture

MESSAGES_URL = "https://graph.facebook.com/v26.0/200000000000002/messages"


@pytest.fixture
async def wa(settings):
    client = WhatsAppClient(settings)
    yield client
    await client.aclose()


def sent_payloads(route) -> list[dict]:
    return [json.loads(call.request.content) for call in route.calls]


@respx.mock
async def test_text_is_echoed_after_mark_read(wa):
    route = respx.post(MESSAGES_URL).mock(
        return_value=httpx.Response(200, json={"messages": [{"id": "wamid.OUT"}], "success": True})
    )
    msg = parse_messages(json.loads(load_fixture("text_message.json")))[0]

    await handle_message(msg, wa)

    read, reply = sent_payloads(route)
    assert read == {"messaging_product": "whatsapp", "status": "read", "message_id": msg.wamid}
    assert reply["to"] == "22890000001"
    assert reply["text"]["body"] == "Reçu : J'ai vendu 3 sacs de riz à Ama"
    assert reply["context"] == {"message_id": msg.wamid}
    assert route.calls[0].request.headers["authorization"] == "Bearer test-token"


@respx.mock
async def test_non_text_gets_unsupported_reply(wa):
    route = respx.post(MESSAGES_URL).mock(
        return_value=httpx.Response(200, json={"messages": [{"id": "wamid.OUT"}]})
    )
    audio = parse_messages(json.loads(load_fixture("mixed_messages.json")))[0]

    await handle_message(audio, wa)

    assert sent_payloads(route)[1]["text"]["body"] == UNSUPPORTED_REPLY


@respx.mock
async def test_api_error_is_raised(wa):
    from app.whatsapp import WhatsAppError

    respx.post(MESSAGES_URL).mock(return_value=httpx.Response(401, json={"error": {"code": 190}}))
    msg = parse_messages(json.loads(load_fixture("text_message.json")))[0]

    with pytest.raises(WhatsAppError):
        await handle_message(msg, wa)
