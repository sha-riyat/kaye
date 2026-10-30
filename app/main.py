"""FastAPI webhook: GET verification, POST receipt with signature check, dedup and background dispatch.

The POST handler does no real work: it validates, deduplicates and hands each message to a
dispatcher (Modal `spawn` in production), so Meta gets its 200 well under a second.
"""

import json
import logging
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import PlainTextResponse

from app.config import Settings, get_settings
from app.dedup import Deduplicator, InMemoryDeduplicator
from app.webhook import InboundMessage, parse_messages, parse_statuses, verify_signature

log = logging.getLogger(__name__)

Dispatcher = Callable[[InboundMessage], Awaitable[None]]


def create_app(
    dispatch: Dispatcher,
    settings: Settings | None = None,
    dedup: Deduplicator | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    dedup = dedup or InMemoryDeduplicator()
    app = FastAPI(title="Kayé", docs_url=None, redoc_url=None)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/webhook")
    async def verify(
        mode: str = Query("", alias="hub.mode"),
        token: str = Query("", alias="hub.verify_token"),
        challenge: str = Query("", alias="hub.challenge"),
    ) -> PlainTextResponse:
        if mode == "subscribe" and settings.whatsapp_verify_token and token == settings.whatsapp_verify_token:
            return PlainTextResponse(challenge)
        raise HTTPException(status_code=403, detail="verification failed")

    @app.post("/webhook")
    async def receive(request: Request) -> Response:
        body = await request.body()
        if not verify_signature(
            body, request.headers.get("x-hub-signature-256"), settings.whatsapp_app_secret
        ):
            log.warning("rejected webhook with invalid signature")
            raise HTTPException(status_code=401, detail="invalid signature")

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="invalid json") from None

        for status in parse_statuses(payload):
            if status.get("status") == "failed":
                log.warning("message %s failed: %s", status.get("id"), status.get("errors"))
            else:
                log.info("message %s %s", status.get("id"), status.get("status"))

        for msg in parse_messages(payload):
            if not await dedup.claim(msg.wamid):
                log.info("duplicate message %s ignored", msg.wamid)
                continue
            await dispatch(msg)

        return Response(status_code=200)

    return app
