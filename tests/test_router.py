import json

import httpx
import pytest
import respx

from app.router import AUDIO_ERROR_REPLY, EMPTY_AUDIO_REPLY, UNSUPPORTED_REPLY, handle_message
from app.transcribe import Transcriber
from app.webhook import parse_messages
from app.whatsapp import WhatsAppClient, WhatsAppError
from tests.conftest import load_fixture

GRAPH = "https://graph.facebook.com/v26.0"
MESSAGES_URL = f"{GRAPH}/200000000000002/messages"
MEDIA_URL = f"{GRAPH}/MEDIA_AUDIO_1"
CDN_URL = "https://lookaside.fbsbx.com/whatsapp_business/attachments/?mid=MEDIA_AUDIO_1"
TRANSCRIBE_URL = "https://api.meta.ai/v1/asr/transcribe"


@pytest.fixture
async def wa(settings):
    client = WhatsAppClient(settings)
    yield client
    await client.aclose()


@pytest.fixture
async def transcriber(settings):
    client = Transcriber(settings)
    yield client
    await client.aclose()


@pytest.fixture
def sent():
    return respx.post(MESSAGES_URL).mock(
        return_value=httpx.Response(200, json={"messages": [{"id": "wamid.OUT"}], "success": True})
    )


def text_msg():
    return parse_messages(json.loads(load_fixture("text_message.json")))[0]


def audio_msg():
    return parse_messages(json.loads(load_fixture("mixed_messages.json")))[0]


def image_msg():
    return parse_messages(json.loads(load_fixture("mixed_messages.json")))[1]


def payloads(route) -> list[dict]:
    return [json.loads(call.request.content) for call in route.calls]


def mock_media(audio: bytes):
    respx.get(MEDIA_URL).mock(
        return_value=httpx.Response(200, json={"url": CDN_URL, "mime_type": "audio/ogg; codecs=opus"})
    )
    return respx.get(CDN_URL).mock(return_value=httpx.Response(200, content=audio))


@respx.mock
async def test_text_is_echoed_after_mark_read(wa, transcriber, sent):
    msg = text_msg()
    await handle_message(msg, wa, transcriber)

    read, reply = payloads(sent)
    assert read == {"messaging_product": "whatsapp", "status": "read", "message_id": msg.wamid}
    assert reply["to"] == "22890000001"
    assert reply["text"]["body"] == "Reçu : J'ai vendu 3 sacs de riz à Ama"
    assert reply["context"] == {"message_id": msg.wamid}
    assert sent.calls[0].request.headers["authorization"] == "Bearer test-token"


@respx.mock
async def test_voice_note_is_downloaded_transcribed_and_echoed(wa, transcriber, sent, voice_note_ogg):
    cdn = mock_media(voice_note_ogg)
    respx.post(TRANSCRIBE_URL).mock(
        return_value=httpx.Response(
            200, json={"transcript": "Ama me doit 5 000 francs", "audioDurationMs": 3000}
        )
    )

    await handle_message(audio_msg(), wa, transcriber)

    assert cdn.calls[0].request.headers["authorization"] == "Bearer test-token"
    assert payloads(sent)[1]["text"]["body"] == "🎙️ J'ai compris : « Ama me doit 5 000 francs »"


@respx.mock
async def test_silent_voice_note_asks_to_resend(wa, transcriber, sent, voice_note_ogg):
    mock_media(voice_note_ogg)
    respx.post(TRANSCRIBE_URL).mock(
        return_value=httpx.Response(200, json={"transcript": "", "audioDurationMs": 1000})
    )

    await handle_message(audio_msg(), wa, transcriber)

    assert payloads(sent)[1]["text"]["body"] == EMPTY_AUDIO_REPLY


@respx.mock
async def test_media_download_failure_gets_polite_reply(wa, transcriber, sent):
    respx.get(MEDIA_URL).mock(return_value=httpx.Response(404, json={"error": {}}))

    await handle_message(audio_msg(), wa, transcriber)

    assert payloads(sent)[1]["text"]["body"] == AUDIO_ERROR_REPLY


@respx.mock
async def test_transcription_failure_gets_polite_reply(wa, transcriber, sent, voice_note_ogg):
    mock_media(voice_note_ogg)
    respx.post(TRANSCRIBE_URL).mock(return_value=httpx.Response(500))

    await handle_message(audio_msg(), wa, transcriber)

    assert payloads(sent)[1]["text"]["body"] == AUDIO_ERROR_REPLY


@respx.mock
async def test_image_gets_unsupported_reply(wa, transcriber, sent):
    await handle_message(image_msg(), wa, transcriber)

    assert payloads(sent)[1]["text"]["body"] == UNSUPPORTED_REPLY


@respx.mock
async def test_reply_goes_out_from_the_number_that_received_the_message(wa, transcriber, sent):
    other = respx.post(f"{GRAPH}/999000000000009/messages").mock(
        return_value=httpx.Response(200, json={"messages": [{"id": "wamid.OUT"}]})
    )
    msg = text_msg().model_copy(update={"phone_number_id": "999000000000009"})

    await handle_message(msg, wa, transcriber)

    assert len(other.calls) == 2  # mark read + reply
    assert sent.calls == []  # nothing from the default number


@respx.mock
async def test_send_error_is_raised(wa, transcriber):
    respx.post(MESSAGES_URL).mock(return_value=httpx.Response(401, json={"error": {"code": 190}}))

    with pytest.raises(WhatsAppError):
        await handle_message(text_msg(), wa, transcriber)
