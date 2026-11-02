"""English for the hackathon judges (temporary).

Merchants in francophone West Africa speak French, so everything Kayé says is written in French by
the code. A shop chooses its language on first contact; when it chooses English, the replies of each
message are translated in ONE model call just before they leave. Document images stay in French.

To remove: delete this module and its calls (router.py, jobs.py), the English shortcuts in
agent/loop.py, and the `shop.language` column.
"""

import json
import logging

from app.agent.reply import Reply
from app.db import queries

log = logging.getLogger(__name__)

FRENCH, ENGLISH = "fr", "en"
CHOOSE = Reply(
    "Bienvenue sur *Kayé* ! Dans quelle langue voulez-vous continuer ?\n"
    "Welcome to *Kayé*! Which language would you like to use?",
    buttons=[("lang:fr", "Français"), ("lang:en", "English")],
)
SET = {
    FRENCH: "C'est noté : je vous réponds en français. Écrivez « langue » pour changer.",
    ENGLISH: "C'est noté : je vous réponds en anglais. Écrivez « langue » pour changer.",
}
WORDS = {
    "francais": FRENCH, "french": FRENCH, "fr": FRENCH,
    "english": ENGLISH, "anglais": ENGLISH, "en": ENGLISH,
}  # fmt: skip
ASK_AGAIN = {"langue", "language", "lang"}

MODEL = "muse-spark-1.3"
PROMPT = """Translate into English each French text in this JSON list. They are WhatsApp messages and
button titles sent by Kayé, the assistant of a small shop in Togo. Keep exactly: WhatsApp formatting
(*bold*, _italic_), line breaks, emojis, numbers and amounts as written (33 000, FCFA), names of people,
shops and products, and links. Translate the buttons too (« Oui, noter » -> « Yes, record »). Keep each
item short when the French one is short. Answer with JSON: {"texts": [...]} in the same order, same count."""
FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "Translation",
        "schema": {"type": "object", "properties": {"texts": {"type": "array", "items": {"type": "string"}}},
                   "required": ["texts"]},
    },
}  # fmt: skip


def choose() -> Reply:
    """A fresh copy: replies are translated in place."""
    return Reply(CHOOSE.text, buttons=list(CHOOSE.buttons))


def chosen(text: str | None) -> str | None:
    """« English », « français »… typed instead of tapping a button."""
    return WORDS.get(queries.norm(text or "").strip(" .!"))


async def localize(models, session, shop_id: int | None, language: str | None, replies: list[Reply]) -> list[Reply]:
    """The replies in the shop's language. French, or any failure: unchanged."""
    if language != ENGLISH or not replies:
        return replies
    slots: list[tuple[Reply, str, int | None]] = []  # (reply, field, index in buttons/rows)
    texts: list[str] = []
    for r in replies:
        if r.text:
            slots.append((r, "text", None))
            texts.append(r.text)
        for i, (_, title) in enumerate(r.buttons):
            slots.append((r, "button", i))
            texts.append(title)
        for i, (_, title, _desc) in enumerate(r.rows):
            slots.append((r, "row", i))
            texts.append(title)
    if not texts:
        return replies
    try:
        response, usage = await models.chat(
            model=MODEL, reasoning_effort="minimal", max_tokens=3000, response_format=FORMAT,
            messages=[{"role": "system", "content": PROMPT},
                      {"role": "user", "content": json.dumps(texts, ensure_ascii=False)}],
        )  # fmt: skip
        english = json.loads(response.choices[0].message.content or "{}").get("texts", [])
    except Exception:
        log.exception("translation failed: replies go out in French")
        return replies
    if len(english) != len(texts):
        log.warning("translation returned %d texts for %d: replies go out in French", len(english), len(texts))
        return replies
    if session is not None:
        await queries.log_model_call(session, shop_id=shop_id, model=usage.model, tokens_in=usage.tokens_in,
                                     tokens_out=usage.tokens_out, cost_usd=usage.cost_usd)  # fmt: skip
    for (reply, field, i), text in zip(slots, english, strict=True):
        if field == "text":
            reply.text = text
        elif field == "button":
            button_id, _ = reply.buttons[i]
            reply.buttons[i] = (button_id, text[:20])
        else:
            row_id, _, desc = reply.rows[i]
            reply.rows[i] = (row_id, text[:24], desc)
    return replies
