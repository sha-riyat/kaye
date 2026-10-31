"""Replay a conversation against the real agent and models, without WhatsApp.

    uv run python -m scripts.replay tests/fixtures/conversations/demo.txt --db postgresql://.../kaye_test

One line = one message from the merchant. Special lines:
    [tap 1]            tap the 1st button / list row of the oldest unanswered proposal (1-based)
    [image path.jpg]   send a photo
    [reset]            wipe the scratch database
Replies are printed with their buttons. The database is recreated, so point it at a scratch one.
Judges can use it to try Kayé without a phone. Needs META_MODEL_API_KEY.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from sqlmodel import SQLModel

from app.agent.loop import Agent
from app.agent.reply import Reply
from app.config import get_settings
from app.db.engine import Database
from app.meta_media import MetaMedia
from app.models_client import ModelClient
from app.router import handle_message
from app.services import Services
from app.transcribe import Transcriber
from app.webhook import InboundMessage

SENDER = "22890000001"


class PrintWhatsApp:
    """Stands in for WhatsAppClient: prints what would be sent."""

    def __init__(self, image: bytes | None = None) -> None:
        self.offered: list[Reply] = []  # replies with buttons, not yet answered
        self.image = image

    def from_number(self, _):
        return self

    async def mark_read(self, _):
        pass

    async def download_media(self, _):
        return self.image or b"", "image/jpeg"

    async def send_text(self, to, body, reply_to=None):
        await self.deliver(to, Reply(body))

    async def deliver(self, to, reply: Reply, reply_to=None):
        if reply.buttons or reply.rows:
            self.offered.append(reply)
        print(f"\033[36mKayé\033[0m {reply.text}")
        if reply.image:
            print(f"      [image {len(reply.image)} octets]")
        for row in reply.rows:
            print(f"      ( ) {row[1]}")
        for _, title in reply.buttons:
            print(f"      [ {title} ]")
        if reply.link:
            print(f"      {reply.link}")

    async def aclose(self):
        pass


async def main(path: Path, db_url: str) -> None:
    settings = get_settings()
    db = Database(db_url)
    wa = PrintWhatsApp()
    svc = Services(
        settings, wa, Transcriber(settings), db, Agent(ModelClient(settings)), storage=None, media=MetaMedia(settings)
    )

    async def reset() -> None:
        async with db.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
            await conn.run_sync(SQLModel.metadata.create_all)

    await reset()
    n = 0
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        n += 1
        fields: dict = {"type": "text", "raw_type": "text", "text": line}
        if line == "[reset]":
            await reset()
            continue
        if line.startswith("[tap "):
            index = int(line[5:-1]) - 1
            offer = wa.offered.pop(0)
            choices = [b[0] for b in offer.buttons] + [r[0] for r in offer.rows]
            fields = {"type": "button", "raw_type": "interactive", "button_id": choices[index], "text": "tap"}
            print(f"\033[33mVous\033[0m (touche {choices[index]})")
        elif line.startswith("[image "):
            wa.image = Path(line[7:-1]).read_bytes()
            fields = {"type": "image", "raw_type": "image", "media_id": "M", "text": None}
            print(f"\033[33mVous\033[0m (photo {line[7:-1]})")
        else:
            wa.offered.clear()
            print(f"\n\033[33mVous\033[0m {line}")
        msg = InboundMessage(
            wamid=f"wamid.replay.{n}",
            sender=SENDER,
            phone_number_id="PNID",
            profile_name="Replay",
            timestamp=n,
            **fields,
        )
        await handle_message(msg, svc)
    await svc.agent.models.aclose()
    await db.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("conversation", type=Path)
    parser.add_argument("--db", required=True, help="scratch Postgres URL (it is wiped)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main(args.conversation, args.db))
    sys.exit(0)
