"""Modal app: public webhook endpoint + background message processing.

Dev:    uv run modal serve modal_app.py
Deploy: uv run modal deploy modal_app.py
"""

import modal

app = modal.App("kaye")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("ffmpeg", "chromium", "fonts-liberation")
    .uv_sync(extra_options="--no-dev")
    .add_local_python_source("app")
    .add_local_dir("assets/brand", remote_path="/root/assets/brand")
)
secrets = [modal.Secret.from_name("kaye-secrets")]


# No automatic retries: a retried job could send the same reply (or write the same entry) twice.
@app.function(image=image, secrets=secrets, timeout=300)
async def process_message(message: dict) -> None:
    import logging

    from app.config import get_settings
    from app.router import handle_message
    from app.services import Services
    from app.webhook import InboundMessage

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    svc = Services.build(get_settings())
    try:
        await handle_message(InboundMessage.model_validate(message), svc)
    finally:
        await svc.aclose()


# Hourly: sends each shop its evening summary at its own hour, and supplier reminders the day before
# they fall due. Also keeps the Supabase project awake.
@app.function(image=image, secrets=secrets, timeout=600, schedule=modal.Cron("0 * * * *"))
async def hourly_jobs() -> None:
    import logging

    from app.config import get_settings
    from app.jobs import run_hourly
    from app.services import Services

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    svc = Services.build(get_settings())
    try:
        await run_hourly(svc)
    finally:
        await svc.aclose()


# One warm container: Meta expects an answer in about a second, which a cold start would miss.
@app.function(image=image, secrets=secrets, min_containers=1)
@modal.concurrent(max_inputs=50)
@modal.asgi_app(label="kaye-webhook")
def web():
    import logging

    from app.config import get_settings
    from app.dedup import ModalDictDeduplicator, PostgresDeduplicator
    from app.main import create_app
    from app.webhook import InboundMessage

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = get_settings()

    if settings.database_url:
        from app.db.engine import Database

        dedup = PostgresDeduplicator(Database(settings.database_url))
    else:
        dedup = ModalDictDeduplicator()

    async def dispatch(msg: InboundMessage) -> None:
        await process_message.spawn.aio(msg.model_dump())

    return create_app(dispatch=dispatch, settings=settings, dedup=dedup)
