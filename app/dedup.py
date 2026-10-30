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


class ModalDictDeduplicator:
    """Dedup shared across Modal containers, using an atomic put-if-absent on a modal.Dict."""

    def __init__(self, name: str = "kaye-processed-messages") -> None:
        import modal

        self._dict = modal.Dict.from_name(name, create_if_missing=True)

    async def claim(self, wamid: str) -> bool:
        return await self._dict.put.aio(wamid, True, skip_if_exists=True)
