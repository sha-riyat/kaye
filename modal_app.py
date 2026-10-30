"""Modal app: public webhook endpoint + background message processing.

Dev:    uv run modal serve modal_app.py
Deploy: uv run modal deploy modal_app.py
"""

import modal

app = modal.App("kaye")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("ffmpeg")
    .uv_sync(extra_options="--no-dev")
    .add_local_python_source("app")
)
secrets = [modal.Secret.from_name("kaye-secrets")]


# No automatic retries: a retried job could send the same reply (or later, write the same entry) twice.
@app.function(image=image, secrets=secrets, timeout=300)
async def process_message(message: dict) -> None:
    from app.config import get_settings
    from app.router import handle_message
    from app.transcribe import Transcriber
    from app.webhook import InboundMessage
    from app.whatsapp import WhatsAppClient

    settings = get_settings()
    wa, transcriber = WhatsAppClient(settings), Transcriber(settings)
    try:
        await handle_message(InboundMessage.model_validate(message), wa, transcriber)
    finally:
        await wa.aclose()
        await transcriber.aclose()


@app.function(image=image, secrets=secrets)
@modal.concurrent(max_inputs=50)
@modal.asgi_app(label="kaye-webhook")
def web():
    import logging

    from app.dedup import ModalDictDeduplicator
    from app.main import create_app
    from app.webhook import InboundMessage

    logging.basicConfig(level=logging.INFO)

    async def dispatch(msg: InboundMessage) -> None:
        await process_message.spawn.aio(msg.model_dump())

    return create_app(dispatch=dispatch, dedup=ModalDictDeduplicator())
