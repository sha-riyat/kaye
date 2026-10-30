"""Routes an inbound message to its handler. For now: echo text, acknowledge everything else."""

import logging

from app.webhook import InboundMessage
from app.whatsapp import WhatsAppClient

log = logging.getLogger(__name__)

UNSUPPORTED_REPLY = (
    "Pour le moment, je ne comprends que les messages écrits. Les vocaux et photos arrivent bientôt !"
)


async def handle_message(msg: InboundMessage, wa: WhatsAppClient) -> None:
    log.info("handling %s message %s from %s", msg.type, msg.wamid, msg.sender)
    await wa.mark_read(msg.wamid)

    if msg.type == "text" and msg.text:
        await wa.send_text(msg.sender, f"Reçu : {msg.text}", reply_to=msg.wamid)
    else:
        await wa.send_text(msg.sender, UNSUPPORTED_REPLY, reply_to=msg.wamid)
