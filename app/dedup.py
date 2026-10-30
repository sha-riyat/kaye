"""Deduplication by WhatsApp message id (Meta retries webhooks, and may deliver twice)."""

from typing import Protocol


class Deduplicator(Protocol):
    async def claim(self, wamid: str) -> bool:
        """Return True the first time a wamid is seen, False afterwards."""
        ...


class InMemoryDeduplicator:
    """Single-process dedup, for tests and local runs."""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    async def claim(self, wamid: str) -> bool:
        if wamid in self._seen:
            return False
        self._seen.add(wamid)
        return True


class PostgresDeduplicator:
    """Dedup through the `processed_message` table (atomic insert-if-absent)."""

    def __init__(self, db) -> None:  # app.db.engine.Database, imported lazily to keep the webhook light
        self._db = db

    async def claim(self, wamid: str) -> bool:
        from sqlalchemy.dialects.postgresql import insert

        from app.db.models import ProcessedMessage

        stmt = (
            insert(ProcessedMessage)
            .values(wamid=wamid)
            .on_conflict_do_nothing(index_elements=["wamid"])
            .returning(ProcessedMessage.wamid)
        )
        async with self._db.session() as session:
            result = await (await session.connection()).execute(stmt)
            return result.first() is not None


class ModalDictDeduplicator:
    """Dedup shared across Modal containers, using an atomic put-if-absent on a modal.Dict."""

    def __init__(self, name: str = "kaye-processed-messages") -> None:
        import modal

        self._dict = modal.Dict.from_name(name, create_if_missing=True)

    async def claim(self, wamid: str) -> bool:
        return await self._dict.put.aio(wamid, True, skip_if_exists=True)
