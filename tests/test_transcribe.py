import json
import wave
from io import BytesIO

import httpx
import pytest
import respx

from app.transcribe import Transcriber, TranscriptionError, to_wav

TRANSCRIBE_URL = "https://api.meta.ai/v1/asr/transcribe"


async def test_ogg_opus_is_converted_to_16k_mono_pcm_wav(voice_note_ogg):
    wav = await to_wav(voice_note_ogg)
    with wave.open(BytesIO(wav)) as w:
        assert w.getnchannels() == 1
        assert w.getframerate() == 16000
        assert w.getsampwidth() == 2
        assert 0.9 < w.getnframes() / w.getframerate() < 1.1


async def test_garbage_audio_raises():
    with pytest.raises(TranscriptionError):
        await to_wav(b"not audio at all")


@respx.mock
async def test_transcribe_sends_multipart_wav_and_parses_transcript(settings, voice_note_ogg):
    route = respx.post(TRANSCRIBE_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "sessionId": "s1",
                "transcript": " J'ai vendu trois sacs de riz à Ama. ",
                "audioDurationMs": 4000,
                "turns": [],
            },
        )
    )
    transcriber = Transcriber(settings)
    try:
        result = await transcriber.transcribe(voice_note_ogg)
    finally:
        await transcriber.aclose()

    assert result.text == "J'ai vendu trois sacs de riz à Ama."
    assert result.audio_duration_ms == 4000
    assert result.cost_usd == pytest.approx(0.0002)

    request = route.calls[0].request
    assert request.headers["authorization"] == "Bearer test-meta-key"
    body = request.content
    assert b'name="request"' in body and b'name="audio"' in body
    assert b"audio/wav" in body and b"RIFF" in body
    settings_part = body.split(b'name="request"')[1].split(b"\r\n\r\n", 1)[1].split(b"\r\n--")[0]
    sent = json.loads(settings_part)
    assert sent["model"] == "muse-voice-transcribe-1.0"
    assert sent["audioEncoding"] == "WAV"
    assert sent["languageBias"] == ["French"]
    assert "FCFA" in sent["keywords"]


@respx.mock
async def test_transcribe_api_error_raises(settings, voice_note_ogg):
    respx.post(TRANSCRIBE_URL).mock(return_value=httpx.Response(400, json={"error": "bad audio"}))
    transcriber = Transcriber(settings)
    try:
        with pytest.raises(TranscriptionError):
            await transcriber.transcribe(voice_note_ogg)
    finally:
        await transcriber.aclose()
