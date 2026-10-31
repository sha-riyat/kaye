"""Minimal WhatsApp Cloud API client."""

import logging

import httpx

from app.agent.reply import Reply
from app.config import Settings

log = logging.getLogger(__name__)


class WhatsAppError(Exception):
    pass


class WhatsAppClient:
    def __init__(
        self,
        settings: Settings,
        http: httpx.AsyncClient | None = None,
        phone_number_id: str | None = None,
    ) -> None:
        self._settings = settings
        self._http = http or httpx.AsyncClient(timeout=20)
        self._base_url = f"{settings.whatsapp_graph_base_url}/{settings.whatsapp_api_version}"
        self.phone_number_id = phone_number_id or settings.whatsapp_phone_number_id
        self._messages_url = f"{self._base_url}/{self.phone_number_id}/messages"

    def from_number(self, phone_number_id: str) -> "WhatsAppClient":
        """Same client sending from another of our numbers (replies go out from the number that was
        written to). Shares the HTTP connection pool."""
        if not phone_number_id or phone_number_id == self.phone_number_id:
            return self
        return WhatsAppClient(self._settings, self._http, phone_number_id)

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

    async def send_buttons(
        self, to: str, body: str, buttons: list[tuple[str, str]], reply_to: str | None = None
    ) -> str:
        """Up to 3 quick-reply buttons: (id, title)."""
        interactive = {
            "type": "button",
            "body": {"text": body[:1024]},
            "action": {"buttons": [{"type": "reply", "reply": {"id": i, "title": title}} for i, title in buttons]},
        }
        return await self._send_interactive(to, interactive, reply_to)

    async def send_list(
        self,
        to: str,
        body: str,
        rows: list[tuple[str, str, str]],
        button: str = "Choisir",
        reply_to: str | None = None,
    ) -> str:
        """A list of up to 10 choices: (id, title <= 24 chars, description)."""
        row_payload = [{"id": i, "title": title[:24], **({"description": d[:72]} if d else {})} for i, title, d in rows]
        interactive = {
            "type": "list",
            "body": {"text": body[:1024]},
            "action": {"button": button[:20], "sections": [{"title": "Choix", "rows": row_payload}]},
        }
        return await self._send_interactive(to, interactive, reply_to)

    async def _send_interactive(self, to: str, interactive: dict, reply_to: str | None) -> str:
        payload: dict = {
            "messaging_product": "whatsapp", "recipient_type": "individual", "to": to,
            "type": "interactive", "interactive": interactive,
        }  # fmt: skip
        if reply_to:
            payload["context"] = {"message_id": reply_to}
        return (await self._post(payload))["messages"][0]["id"]

    async def upload_media(self, data: bytes, mime_type: str, filename: str) -> str:
        response = await self._http.post(
            f"{self._base_url}/{self.phone_number_id}/media",
            headers=self._auth,
            data={"messaging_product": "whatsapp", "type": mime_type},
            files={"file": (filename, data, mime_type)},
        )
        if response.is_error:
            raise WhatsAppError(f"media upload {response.status_code}: {response.text}")
        return response.json()["id"]

    async def send_image(self, to: str, data: bytes, caption: str = "", reply_to: str | None = None) -> str:
        media_id = await self.upload_media(data, "image/png", "recu.png")
        payload: dict = {
            "messaging_product": "whatsapp", "recipient_type": "individual", "to": to, "type": "image",
            "image": {"id": media_id, **({"caption": caption[:1024]} if caption else {})},
        }  # fmt: skip
        if reply_to:
            payload["context"] = {"message_id": reply_to}
        return (await self._post(payload))["messages"][0]["id"]

    async def send_template(self, to: str, name: str, params: list[str], language: str = "fr") -> str:
        """An approved template: the only way to write first, outside the 24 h window."""
        components = [{"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}] if params else []
        payload = {
            "messaging_product": "whatsapp", "to": to, "type": "template",
            "template": {"name": name, "language": {"code": language}, "components": components},
        }  # fmt: skip
        return (await self._post(payload))["messages"][0]["id"]

    async def deliver(self, to: str, reply: Reply, reply_to: str | None = None) -> None:
        """Send a Reply in the richest form WhatsApp allows."""
        text = reply.text + (f"\n\n{reply.link}" if reply.link else "")
        if reply.image:
            await self.send_image(to, reply.image, text, reply_to)
        elif reply.rows:
            await self.send_list(to, text, reply.rows, reply.list_button, reply_to)
        elif reply.buttons:
            await self.send_buttons(to, text, reply.buttons, reply_to)
        elif text:
            await self.send_text(to, text, reply_to)

    async def mark_read(self, wamid: str) -> None:
        await self._post({"messaging_product": "whatsapp", "status": "read", "message_id": wamid})

    async def _post(self, payload: dict) -> dict:
        response = await self._http.post(self._messages_url, json=payload, headers=self._auth)
        if response.is_error:
            raise WhatsAppError(f"{response.status_code}: {response.text}")
        return response.json()
