"""Routes an inbound message: onboarding, voice, photo, text, button taps.

State is committed before any reply leaves, so a merchant tapping "Oui" always finds the pending
action in the database.
"""

import logging
from dataclasses import dataclass, field

from app.agent import actions
from app.agent.actions import Ctx
from app.agent.prompts import AFTER_NAME, DEMO_NOTICE, WELCOME
from app.agent.reply import Reply
from app.db import queries
from app.db.models import Entry, EntrySource, Media, PendingStatus, Receipt, Shop
from app.receipts import RenderError, extra_height, receipt_data, render_png, shop_card
from app.services import Services
from app.storage import media_key
from app.transcribe import TranscriptionError
from app.webhook import InboundMessage
from app.whatsapp import WhatsAppError

log = logging.getLogger(__name__)

AUDIO_ERROR_REPLY = "Désolé, je n'ai pas pu écouter ce vocal. Pouvez-vous réessayer ou l'écrire ?"
EMPTY_AUDIO_REPLY = "Je n'ai rien entendu dans ce vocal. Pouvez-vous le renvoyer ?"
IMAGE_ERROR_REPLY = "Je n'ai pas réussi à ouvrir cette photo. Pouvez-vous la renvoyer ?"
UNSUPPORTED_REPLY = "Pour le moment, je comprends les messages écrits, les vocaux et les photos."
EXPIRED_REPLY = "Cette proposition n'est plus valable (plus de 30 minutes). Redites-la-moi, je la refais."
QUOTA_REPLY = "Vous avez beaucoup écrit aujourd'hui : je reprends demain. À très vite !"
BUDGET_REPLY = "Je suis très sollicité en ce moment. Pouvez-vous réessayer un peu plus tard ?"
NAME_FIRST_REPLY = "Avant de commencer : comment s'appelle votre boutique ? (quelques mots suffisent)"
SHOP_NAME_MAX = 60


@dataclass
class Outcome:
    replies: list[Reply] = field(default_factory=list)


async def handle_message(msg: InboundMessage, svc: Services) -> None:
    log.info("handling %s message %s from %s", msg.type, msg.wamid, msg.sender)
    wa = svc.wa.from_number(msg.phone_number_id)
    await wa.mark_read(msg.wamid)

    text, source, media_bytes, mime = msg.text, EntrySource.TEXT, None, ""
    try:
        if msg.type == "audio" and msg.media_id:
            media_bytes, mime = await wa.download_media(msg.media_id)
            mime = mime or "audio/ogg"
            transcript = await svc.transcriber.transcribe(media_bytes)
            if not transcript.text:
                await wa.send_text(msg.sender, EMPTY_AUDIO_REPLY, reply_to=msg.wamid)
                return
            text, source = transcript.text, EntrySource.VOICE
            log.info("voice note %s: %s", msg.wamid, text)
        elif msg.type == "image" and msg.media_id:
            media_bytes, mime = await wa.download_media(msg.media_id)
            mime = mime or "image/jpeg"
    except TranscriptionError:
        log.exception("voice note %s failed", msg.wamid)
        await wa.send_text(msg.sender, AUDIO_ERROR_REPLY, reply_to=msg.wamid)
        return
    except WhatsAppError:
        log.exception("media download for %s failed", msg.wamid)
        await wa.send_text(
            msg.sender, IMAGE_ERROR_REPLY if msg.type == "image" else AUDIO_ERROR_REPLY, reply_to=msg.wamid
        )
        return

    outcome = Outcome()
    try:
        async with svc.db.session() as session:
            outcome.replies = await _process(session, svc, msg, text, source, media_bytes, mime)
    except Exception:
        log.exception("processing %s failed", msg.wamid)
        outcome.replies = [
            Reply("Désolé, un problème est survenu de mon côté. Rien n'a été noté. Pouvez-vous réessayer ?")
        ]

    for reply in outcome.replies:
        try:
            await wa.deliver(msg.sender, reply, reply_to=msg.wamid)
        except WhatsAppError:
            log.exception("could not deliver a reply to %s", msg.sender)


async def _process(session, svc: Services, msg: InboundMessage, text: str | None, source: str,
                   media_bytes: bytes | None, mime: str) -> list[Reply]:  # fmt: skip
    user = await queries.user_by_whatsapp(session, msg.sender)
    if user is None:
        await queries.create_shop_with_owner(session, msg.sender, msg.profile_name)
        return [Reply(WELCOME), Reply(DEMO_NOTICE)]
    shop = await session.get(Shop, user.shop_id)

    if not shop.name:
        return await _name_shop(session, shop, text if msg.type in ("text", "audio") else None)

    ctx = Ctx(session=session, shop=shop, user=user, wamid=msg.wamid, source=source)
    replies = await _handle(ctx, svc, msg, text, media_bytes, mime)
    said = (
        text if msg.type in ("text", "audio") else ("[photo]" if msg.type == "image" else f"[{msg.text or 'bouton'}]")
    )
    await queries.remember(session, shop.id, user.id, "merchant", said or "")
    for reply in replies:
        await queries.remember(session, shop.id, user.id, "kaye", reply.text)
    return replies


async def _handle(ctx: Ctx, svc: Services, msg: InboundMessage, text: str | None,
                  media_bytes: bytes | None, mime: str) -> list[Reply]:  # fmt: skip
    if msg.type == "button" and msg.button_id:
        return await _on_button(ctx, svc, msg.button_id)

    if msg.type == "image" and media_bytes:
        if msg.text and "logo" in msg.text.lower():
            return [await _save_logo(ctx, svc, media_bytes, mime)]
        if (blocked := await _guard(ctx, svc)) is not None:
            return [blocked]
        ctx.source = EntrySource.NOTEBOOK_PHOTO
        ctx.media_id = await _store_media(ctx, svc, "image", media_bytes, mime, msg.media_id)
        replies = await svc.agent.on_image(ctx, media_bytes, mime, msg.text)
        return replies

    if text:
        if (blocked := await _guard(ctx, svc)) is not None:
            return [blocked]
        if msg.type == "audio" and media_bytes:
            ctx.media_id = await _store_media(ctx, svc, "audio", media_bytes, mime, msg.media_id)
        return await svc.agent.on_text(ctx, text)

    return [Reply(UNSUPPORTED_REPLY)]


async def _guard(ctx: Ctx, svc: Services) -> Reply | None:
    """Abuse protection: anyone can write to the number, so cap per-shop messages and total spend."""
    if await queries.calls_today(ctx.session, ctx.shop.id) >= svc.settings.daily_message_quota_per_user:
        return Reply(QUOTA_REPLY)
    if await queries.spent_today(ctx.session) >= svc.settings.global_daily_model_budget_usd:
        return Reply(BUDGET_REPLY)
    return None


async def _name_shop(session, shop: Shop, text: str | None) -> list[Reply]:
    name = (text or "").strip().strip("«»\"'").strip()
    if not name or len(name) > SHOP_NAME_MAX or "\n" in name:
        return [Reply(NAME_FIRST_REPLY)]
    shop.name = name
    session.add(shop)
    return [Reply(AFTER_NAME.format(name=name))]


async def _store_media(
    ctx: Ctx, svc: Services, kind: str, data: bytes, mime: str, wa_media_id: str | None
) -> int | None:
    if svc.storage is None:
        log.warning("R2 is not configured: %s not stored", kind)
        return None
    try:
        key = media_key(ctx.shop.id, kind, mime)
        await svc.storage.put(key, data, mime)
        log.info("stored %s in R2 as %s", kind, key)
        media = Media(shop_id=ctx.shop.id, kind=kind, storage_key=key, mime_type=mime, wa_media_id=wa_media_id)
        ctx.session.add(media)
        await ctx.session.flush()
        return media.id
    except Exception:
        log.exception("could not store media")
        return None


async def _save_logo(ctx: Ctx, svc: Services, data: bytes, mime: str) -> Reply:
    if svc.storage is None:
        return Reply("Je ne peux pas encore enregistrer de logo. Vos reçus porteront l'initiale de votre boutique.")
    key = media_key(ctx.shop.id, "logo", mime)
    await svc.storage.put(key, data, mime)
    ctx.shop.logo_key = key
    ctx.session.add(ctx.shop)
    return Reply("Merci ! Votre logo sera sur tous vos prochains reçus. ✅")


# --- button taps ---


async def _on_button(ctx: Ctx, svc: Services, button_id: str) -> list[Reply]:
    action, _, rest = button_id.partition(":")
    if action == "rem":
        from app.db.models import Contact

        contact = await ctx.session.get(Contact, int(rest)) if rest.isdigit() else None
        if contact is None or contact.shop_id != ctx.shop.id:
            return [Reply("Je ne retrouve plus ce client.")]
        return [await actions.reminder_for(ctx, contact)]

    pending_id, _, extra = rest.partition(":")
    pending = await queries.get_pending(ctx.session, ctx.shop.id, int(pending_id)) if pending_id.isdigit() else None
    if pending is None or pending.status != PendingStatus.PENDING:
        return [Reply("Cette proposition a déjà été traitée.")]
    if pending.expires_at < queries.utcnow():
        await queries.settle_pending(ctx.session, pending, PendingStatus.EXPIRED)
        return [Reply(EXPIRED_REPLY)]

    subs = await _batch_items(ctx, pending)
    if action == "no":
        for item in [pending, *subs]:
            await queries.settle_pending(ctx.session, item, PendingStatus.CANCELLED)
        return [Reply("D'accord, j'annule. Rien n'est noté.")]
    if action == "fix":
        for item in subs:
            await queries.settle_pending(ctx.session, item, PendingStatus.CANCELLED)
        await actions.mark_corrected(ctx, pending)
        return [Reply("Dites-moi ce qu'il faut changer (par vocal ou par écrit), je refais la proposition.")]
    if action == "pick":
        return [await actions.pick_party(ctx, pending, extra)]
    if action == "ok":
        return await _confirm(ctx, svc, pending)
    return [Reply("Je n'ai pas compris ce bouton.")]


async def _batch_items(ctx: Ctx, pending) -> list:
    if pending.kind != "batch":
        return []
    items = [await queries.get_pending(ctx.session, ctx.shop.id, i) for i in pending.payload["ids"]]
    return [i for i in items if i is not None and i.status == PendingStatus.PENDING]


async def _confirm(ctx: Ctx, svc: Services, pending) -> list[Reply]:
    """Apply one proposal, or every operation of a grouped recap, then send one confirmation."""
    items = await _batch_items(ctx, pending) if pending.kind == "batch" else [pending]
    texts, receipts = [], []
    for item in items:
        applied = await actions.apply_pending(ctx, item)
        await queries.settle_pending(ctx.session, item, PendingStatus.CONFIRMED)
        texts.append(applied.reply.text)
        if applied.sale_entry_id:
            receipts.append(await _receipt_reply(ctx, svc, applied.sale_entry_id))
    if pending.kind == "batch":
        await queries.settle_pending(ctx.session, pending, PendingStatus.CONFIRMED)
    if not texts:
        return [Reply("Cette proposition a déjà été traitée.")]
    return [Reply("\n".join(texts)), *receipts]


async def _receipt_reply(ctx: Ctx, svc: Services, entry_id: int) -> Reply:
    """The receipt image for a sale. A rendering failure never undoes the sale."""
    entry = await ctx.session.get(Entry, entry_id)
    try:
        owner = await queries.owner_of(ctx.session, ctx.shop.id)
        logo = None
        if ctx.shop.logo_key and svc.storage is not None:
            try:
                logo = await svc.storage.get(ctx.shop.logo_key)
            except Exception:
                log.exception("logo unavailable")
        number = await queries.next_receipt_number(ctx.session, ctx.shop.id)
        customer = ""
        if entry.contact_id:
            from app.db.models import Contact

            contact = await ctx.session.get(Contact, entry.contact_id)
            customer = contact.name if contact else ""
        data = receipt_data(
            shop_card(ctx.shop, owner.whatsapp_id if owner else None, logo), entry, number, customer, ctx.now
        )
        png = await render_png("recu_ticket.html.j2", data, extra_height(len(entry.lines)))
        key = ""
        if svc.storage is not None:
            key = media_key(ctx.shop.id, "receipt", "image/png")
            await svc.storage.put(key, png, "image/png")
        ctx.session.add(Receipt(shop_id=ctx.shop.id, entry_id=entry.id, number=number, image_key=key))
        who = f" pour {customer}" if customer else ""
        return Reply(f"Reçu n° {number:04d}{who}. Transférez-le à votre client ↗", image=png)
    except (RenderError, OSError):
        log.exception("receipt rendering failed for entry %s", entry_id)
        return Reply("Je n'ai pas pu préparer l'image du reçu, mais la vente est bien notée.")
