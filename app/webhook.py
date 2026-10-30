"""WhatsApp webhook payloads: signature check and parsing into normalized inbound messages."""

import hashlib
import hmac
from typing import Any, Literal

from pydantic import BaseModel

MessageType = Literal["text", "audio", "image", "button", "unsupported"]


class InboundMessage(BaseModel):
    """One message from a merchant, flattened from the nested webhook payload."""

    wamid: str
    sender: str  # WhatsApp id (phone number without "+")
    phone_number_id: str  # our business number that received it
    profile_name: str | None = None
    timestamp: int
    type: MessageType
    raw_type: str
    text: str | None = None
    media_id: str | None = None
    mime_type: str | None = None
    button_id: str | None = None


def verify_signature(body: bytes, header: str | None, app_secret: str) -> bool:
    """Check `X-Hub-Signature-256: sha256=<hex>` against an HMAC of the raw body. Fails closed."""
    if not app_secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


def parse_messages(payload: dict[str, Any]) -> list[InboundMessage]:
    """Extract user messages; status updates (sent/delivered/read) are ignored."""
    if payload.get("object") != "whatsapp_business_account":
        return []

    messages: list[InboundMessage] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "messages":
                continue
            value = change.get("value", {})
            phone_number_id = value.get("metadata", {}).get("phone_number_id", "")
            names = {c.get("wa_id"): c.get("profile", {}).get("name") for c in value.get("contacts", [])}
            for msg in value.get("messages", []):
                messages.append(_normalize(msg, phone_number_id, names.get(msg.get("from"))))
    return messages


def _normalize(msg: dict[str, Any], phone_number_id: str, profile_name: str | None) -> InboundMessage:
    raw_type = msg.get("type", "")
    fields: dict[str, Any] = {"type": "unsupported"}

    if raw_type == "text":
        fields = {"type": "text", "text": msg["text"]["body"]}
    elif raw_type in ("audio", "image"):
        media = msg[raw_type]
        fields = {
            "type": raw_type,
            "media_id": media["id"],
            "mime_type": media.get("mime_type"),
            "text": media.get("caption"),
        }
    elif raw_type == "interactive":
        interactive = msg["interactive"]
        reply = interactive.get("button_reply") or interactive.get("list_reply")
        if reply:
            fields = {"type": "button", "button_id": reply["id"], "text": reply.get("title")}
    elif raw_type == "button":  # quick-reply button on a template message
        fields = {
            "type": "button",
            "button_id": msg["button"].get("payload"),
            "text": msg["button"].get("text"),
        }

    return InboundMessage(
        wamid=msg["id"],
        sender=msg["from"],
        phone_number_id=phone_number_id,
        profile_name=profile_name,
        timestamp=int(msg.get("timestamp", 0)),
        raw_type=raw_type,
        **fields,
    )
