"""Minimal WhatsApp Cloud API client."""

import logging

import httpx

from app.config import Settings

log = logging.getLogger(__name__)


class WhatsAppError(Exception):
    pass


class WhatsAppClient:
    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._http = http or httpx.AsyncClient(timeout=20)
        self._base_url = f"{settings.whatsapp_graph_base_url}/{settings.whatsapp_api_version}"
        self._messages_url = f"{self._base_url}/{settings.whatsapp_phone_number_id}/messages"

    @property
    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._settings.whatsapp_access_token}"}

    async def aclose(self) -> None:
        await self._http.aclose()

    async def download_media(self, media_id: str) -> tuple[bytes, str]:
        """Fetch a media file sent by the merchant. Returns (bytes, mime type).

        Two steps: the media id resolves to a short-lived URL, which also needs the bearer token.
        """
        meta = await self._http.get(f"{self._base_url}/{media_id}", headers=self._auth)
        if meta.is_error:
            raise WhatsAppError(f"media lookup {meta.status_code}: {meta.text}")
        info = meta.json()

        file = await self._http.get(info["url"], headers=self._auth, follow_redirects=True)
        if file.is_error:
            raise WhatsAppError(f"media download {file.status_code}")
        return file.content, info.get("mime_type", "")

    async def send_text(self, to: str, body: str, reply_to: str | None = None) -> str:
        """Send a free-form text (only allowed inside the 24h window). Returns the new wamid."""
        payload: dict = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"body": body, "preview_url": False},
        }
        if reply_to:
            payload["context"] = {"message_id": reply_to}
        data = await self._post(payload)
        wamid = data["messages"][0]["id"]
        log.info("sent %s to %s", wamid, to)
        return wamid

    async def mark_read(self, wamid: str) -> None:
        await self._post({"messaging_product": "whatsapp", "status": "read", "message_id": wamid})

    async def _post(self, payload: dict) -> dict:
        response = await self._http.post(self._messages_url, json=payload, headers=self._auth)
        if response.is_error:
            raise WhatsAppError(f"{response.status_code}: {response.text}")
        return response.json()
