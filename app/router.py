"""Routes an inbound message to its handler. For now: echo text and transcribed voice notes."""

import logging

from app.transcribe import Transcriber, TranscriptionError
from app.webhook import InboundMessage
from app.whatsapp import WhatsAppClient, WhatsAppError

log = logging.getLogger(__name__)

UNSUPPORTED_REPLY = (
    "Pour le moment, je comprends les messages écrits et les vocaux. Les photos arrivent bientôt !"
)
EMPTY_AUDIO_REPLY = "Je n'ai rien entendu dans ce vocal. Pouvez-vous le renvoyer ?"
AUDIO_ERROR_REPLY = "Désolé, je n'ai pas pu écouter ce vocal. Pouvez-vous réessayer ou l'écrire ?"


async def handle_message(msg: InboundMessage, wa: WhatsAppClient, transcriber: Transcriber) -> None:
    log.info("handling %s message %s from %s", msg.type, msg.wamid, msg.sender)
    wa = wa.from_number(msg.phone_number_id)
    await wa.mark_read(msg.wamid)

    if msg.type == "text" and msg.text:
        await wa.send_text(msg.sender, f"Reçu : {msg.text}", reply_to=msg.wamid)
    elif msg.type == "audio" and msg.media_id:
        await _handle_audio(msg, wa, transcriber)
    else:
        await wa.send_text(msg.sender, UNSUPPORTED_REPLY, reply_to=msg.wamid)


async def _handle_audio(msg: InboundMessage, wa: WhatsAppClient, transcriber: Transcriber) -> None:
    try:
        audio, _ = await wa.download_media(msg.media_id)
        transcript = await transcriber.transcribe(audio)
    except (WhatsAppError, TranscriptionError):
        log.exception("voice note %s failed", msg.wamid)
        await wa.send_text(msg.sender, AUDIO_ERROR_REPLY, reply_to=msg.wamid)
        return

    if not transcript.text:
        await wa.send_text(msg.sender, EMPTY_AUDIO_REPLY, reply_to=msg.wamid)
        return
    await wa.send_text(msg.sender, f"🎙️ J'ai compris : « {transcript.text} »", reply_to=msg.wamid)
