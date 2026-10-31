"""The collaborators a message needs, built once per background job."""

from dataclasses import dataclass

from app.agent.loop import Agent
from app.config import Settings
from app.db.engine import Database
from app.meta_media import MetaMedia
from app.models_client import ModelClient
from app.storage import Storage
from app.transcribe import Transcriber
from app.whatsapp import WhatsAppClient


@dataclass
class Services:
    settings: Settings
    wa: WhatsAppClient
    transcriber: Transcriber
    db: Database
    agent: Agent
    storage: Storage | None
    media: MetaMedia | None = None

    @classmethod
    def build(cls, settings: Settings) -> "Services":
        models = ModelClient(settings)
        storage = Storage(settings) if settings.r2_account_id and settings.r2_access_key_id else None
        return cls(
            settings,
            WhatsAppClient(settings),
            Transcriber(settings),
            Database(settings.database_url),
            Agent(models),
            storage,
            MetaMedia(settings),
        )

    async def aclose(self) -> None:
        await self.wa.aclose()
        await self.transcriber.aclose()
        await self.agent.models.aclose()
        await self.db.dispose()
        if self.media is not None:
            await self.media.aclose()
