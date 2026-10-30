"""Minimal WhatsApp Cloud API client."""

import httpx

from app.config import Settings


class WhatsAppError(Exception):
    pass


class WhatsAppClient:
    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._http = http or httpx.AsyncClient(timeout=20)
        base = f"{settings.whatsapp_graph_base_url}/{settings.whatsapp_api_version}"
        self._messages_url = f"{base}/{settings.whatsapp_phone_number_id}/messages"

    async def aclose(self) -> None:
        await self._http.aclose()

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
        return data["messages"][0]["id"]

    async def mark_read(self, wamid: str) -> None:
        await self._post({"messaging_product": "whatsapp", "status": "read", "message_id": wamid})

    async def _post(self, payload: dict) -> dict:
        response = await self._http.post(
            self._messages_url,
            json=payload,
            headers={"Authorization": f"Bearer {self._settings.whatsapp_access_token}"},
        )
        if response.is_error:
            raise WhatsAppError(f"{response.status_code}: {response.text}")
        return response.json()
