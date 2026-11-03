"""Routes an inbound message: onboarding, voice, photo, text, button taps.

State is committed before any reply leaves, so a merchant tapping "Oui" always finds the pending
action in the database.
"""

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from sqlmodel import select

from app import language
from app.agent import actions
from app.agent.actions import Ctx
from app.agent.prompts import (
    AFTER_NAME,
    DEMO_CANCEL,
    DEMO_DONE,
    DEMO_RECAP,
    DEMO_SALE,
    HELP,
    NAME_AGAIN,
    START_PHOTO,
    START_VOICE,
    WELCOME,
)
from app.agent.reply import Reply
from app.db import ledger, queries
from app.db.models import Contact, Entry, EntryKind, EntrySource, Media, PendingStatus, Receipt, Shop
from app.meta_media import logo_prompt
from app.receipts import (
    RenderError,
    extra_height,
    receipt_data,
    reminder_data,
    render_png,
    settlement_data,
    shop_card,
    statement_data,
    stock_data,
    summary_data,
    summary_extra_height,
)
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
SHOP_NAME_MAX = 60
GREETINGS = {"bonjour", "bonsoir", "salut", "hello", "coucou", "ok", "oui", "merci", "bjr", "slt", "yo", "hi"}
HELP_WORDS = {"aide", "help", "menu", "exemples", "exemple", "comment ca marche"}
PROFILE_NAME = "name:profile"  # « use my WhatsApp name » while the shop has none
# Right after the name: the three ways in, the first one leading to a receipt within seconds.
START_BUTTONS = [("start:demo", "Essayer un exemple"), ("start:voice", "🎤 Faire un vocal"),
                 ("start:photo", "📸 Photo du cahier")]  # fmt: skip


def name_buttons(profile_name: str | None) -> list[tuple[str, str]]:
    """A one-tap answer to « which name? »: the name on the merchant's WhatsApp profile."""
    name = (profile_name or "").strip()
    return [(PROFILE_NAME, name[:20])] if name and len(name) <= SHOP_NAME_MAX else []


@dataclass
class Outcome:
    replies: list[Reply] = field(default_factory=list)


async def handle_message(msg: InboundMessage, svc: Services) -> None:
    log.info("handling %s message %s from %s", msg.type, msg.wamid, msg.sender)
    wa = svc.wa.from_number(msg.phone_number_id)
    if msg.sender in svc.settings.blocked:
        # No reply, no model call. They just wrote, so Meta now accepts a real block too.
        try:
            await wa.block(msg.sender)
            log.info("blocked %s at Meta", msg.sender)
        except WhatsAppError as exc:
            log.warning("ignored blocked number %s; Meta block failed: %s", msg.sender, exc)
        return
    try:
        await wa.mark_read(msg.wamid)
    except WhatsAppError:
        log.warning("could not mark %s as read", msg.wamid)  # the message still gets its answer

    text, source, media_bytes, mime, voice = msg.text, EntrySource.TEXT, None, "", None
    try:
        if msg.type == "audio" and msg.media_id:
            media_bytes, mime = await wa.download_media(msg.media_id)
            mime = mime or "audio/ogg"
            spoken = "English" if await _language_of(svc, msg.sender) == language.ENGLISH else "French"
            transcript = voice = await svc.transcriber.transcribe(media_bytes, spoken)
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
            outcome.replies = await _process(session, svc, msg, text, source, media_bytes, mime, voice)
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


async def _language_of(svc: Services, wa_id: str) -> str | None:
    """The sender's shop language, to bias the transcription before the message is processed."""
    async with svc.db.session() as session:
        user = await queries.user_by_whatsapp(session, wa_id)
        shop = await session.get(Shop, user.shop_id) if user else None
        return shop.language if shop else None


async def _process(session, svc: Services, msg: InboundMessage, text: str | None, source: str,
                   media_bytes: bytes | None, mime: str, voice=None) -> list[Reply]:  # fmt: skip
    user = await queries.user_by_whatsapp(session, msg.sender)
    if user is None:
        await queries.create_shop_with_owner(session, msg.sender, msg.profile_name)
        return [language.choose()]  # in both languages
    shop = await session.get(Shop, user.shop_id)
    replies, erased = await _respond(session, svc, msg, user, shop, text, source, media_bytes, mime, voice)
    # an erased shop is gone: its translation is logged without it
    return await language.localize(svc.agent.models, session, None if erased else shop.id, shop.language, replies)


async def _respond(session, svc: Services, msg: InboundMessage, user, shop: Shop, text: str | None, source: str,
                   media_bytes: bytes | None, mime: str, voice=None) -> tuple[list[Reply], bool]:  # fmt: skip
    if shop.language is None:
        tapped = msg.button_id or ""
        picked = language.chosen(tapped.partition(":")[2] if tapped.startswith("lang:") else text)
        if picked is None:
            return [language.choose()], False
        shop.language = picked
        session.add(shop)
        return [Reply(WELCOME, buttons=name_buttons(msg.profile_name))], False

    if not shop.name:
        if msg.button_id == PROFILE_NAME:
            text = msg.profile_name
        elif msg.type not in ("text", "audio"):
            text = None
        return await _name_shop(session, shop, text, msg.profile_name), False

    ctx = Ctx(session=session, shop=shop, user=user, wamid=msg.wamid, source=source, media=svc.media)
    if voice is not None:
        await queries.log_model_call(
            session, shop_id=shop.id, model=svc.settings.transcribe_model, tokens_in=0, tokens_out=0,
            cost_usd=voice.cost_usd, audio_ms=voice.audio_duration_ms,
        )  # fmt: skip
    replies = await _handle(ctx, svc, msg, text, media_bytes, mime)
    expanded: list[Reply] = []
    for r in replies:
        if r.kind == "receipt":
            expanded.append(await _receipt_reply(ctx, svc, int(r.text)))
        elif r.kind == "bilan":
            expanded.append(await summary_reply(ctx.session, svc, ctx.shop, r.text, ctx.now))
        elif r.doc:
            expanded.append(await _draw(ctx, svc, r))
        elif r.kind == "logo":
            expanded += await _logo_proposals(ctx, svc)
        else:
            expanded.append(r)
    replies = expanded
    if ctx.erased:
        return replies, True  # the shop and its history are gone: nothing to remember
    said = (
        text if msg.type in ("text", "audio") else ("[photo]" if msg.type == "image" else f"[{msg.text or 'bouton'}]")
    )
    await queries.remember(session, shop.id, user.id, "merchant", said or "")
    for reply in replies:
        await queries.remember(session, shop.id, user.id, "kaye", reply.text)
    return replies, False


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
        said = queries.norm(text).strip(" ?!.")
        if said in language.ASK_AGAIN:
            return [language.choose()]
        if said in HELP_WORDS:
            return [Reply(HELP)]  # no model call
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


async def _name_shop(session, shop: Shop, text: str | None, profile_name: str | None) -> list[Reply]:
    name = (text or "").strip().strip("«»\"'").strip()
    if not name or len(name) > SHOP_NAME_MAX or "\n" in name or queries.norm(name).strip(" !.") in GREETINGS:
        return [Reply(NAME_AGAIN, buttons=name_buttons(profile_name))]
    shop.name = name
    session.add(shop)
    return [Reply(AFTER_NAME.format(name=name), buttons=list(START_BUTTONS))]


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


async def _erase(ctx: Ctx, svc: Services) -> Reply:
    files = 0
    if svc.storage is not None:
        files = await svc.storage.delete_prefix(f"shops/{ctx.shop.id}/")
    await queries.erase_shop_data(ctx.session, ctx.shop.id)
    ctx.erased = True
    log.info("shop %s erased its data (%d files)", ctx.shop.id, files)
    return Reply("C'est fait : toutes vos données sont effacées. Écrivez-moi quand vous voulez pour recommencer.")


LOGO_COUNT = 3


async def _logo_proposals(ctx: Ctx, svc: Services) -> list[Reply]:
    """Three logos drawn by Muse Image; the merchant keeps one with a tap."""
    if svc.media is None or svc.storage is None:
        return [Reply("Je ne peux pas dessiner de logo pour le moment.")]
    try:
        images = await svc.media.logos(logo_prompt(ctx.shop.name), n=LOGO_COUNT)
    except Exception:
        log.exception("logo generation failed")
        return [Reply("Je n'ai pas réussi à dessiner de logo. Réessayez dans un moment.")]
    await queries.log_model_call(ctx.session, shop_id=ctx.shop.id, model="muse-image-1.0", tokens_in=0,
                                 tokens_out=0, cost_usd=0.01 * len(images))  # fmt: skip
    keys = []
    for image in images:
        key = media_key(ctx.shop.id, "logo", "image/png")
        await svc.storage.put(key, image, "image/png")
        keys.append(key)
    pending = await queries.create_pending(
        ctx.session, shop_id=ctx.shop.id, user_id=ctx.user.id, kind="logo", payload={"keys": keys}, wamid=ctx.wamid
    )
    replies = [Reply(f"Logo {i + 1}", image=image) for i, image in enumerate(images)]
    buttons = [(f"logo:{pending.id}:{i}", f"Logo {i + 1}") for i in range(len(images))]
    replies.append(Reply("Lequel préférez-vous ?", buttons=buttons[:3], kind="choice"))
    return replies


# --- button taps ---


async def _on_button(ctx: Ctx, svc: Services, button_id: str) -> list[Reply]:
    action, _, rest = button_id.partition(":")
    if action == "lang" and (picked := language.chosen(rest)):
        ctx.shop.language = picked
        ctx.session.add(ctx.shop)
        return [Reply(language.SET[picked])]
    if action == "start":
        if rest == "voice":
            return [Reply(START_VOICE)]
        if rest == "photo":
            return [Reply(START_PHOTO)]
        return [Reply(DEMO_RECAP, buttons=[("demo:ok", "Oui, noter"), ("demo:no", "Annuler")], kind="proposal")]
    if action == "demo":
        if rest != "ok":
            return [Reply(DEMO_CANCEL)]
        return [await _demo_receipt(ctx, svc), Reply(DEMO_DONE)]
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
    if action == "logo" and pending.kind == "logo" and extra.isdigit():
        keys = pending.payload["keys"]
        ctx.shop.logo_key = keys[min(int(extra), len(keys) - 1)]
        ctx.session.add(ctx.shop)
        await queries.settle_pending(ctx.session, pending, PendingStatus.CONFIRMED)
        return [Reply("C'est votre logo maintenant ! ✅ Il sera sur vos prochains reçus.")]
    if action == "ok":
        return await _confirm(ctx, svc, pending)
    return [Reply("Je n'ai pas compris ce bouton.")]


def _one_confirmation(texts: list[str]) -> str:
    """« C'est noté. » once, then what each operation changed."""
    if len(texts) == 1:
        return texts[0]
    details = [t.removeprefix("C'est noté").lstrip(" .:").strip() for t in texts]
    details = [d[0].upper() + d[1:] for d in details if d]
    return "C'est noté. ✅" + "".join(f"\n• {d}" for d in details)


async def _batch_items(ctx: Ctx, pending) -> list:
    if pending.kind != "batch":
        return []
    items = [await queries.get_pending(ctx.session, ctx.shop.id, i) for i in pending.payload["ids"]]
    return [i for i in items if i is not None and i.status == PendingStatus.PENDING]


async def _confirm(ctx: Ctx, svc: Services, pending) -> list[Reply]:
    """Apply one proposal, or every operation of a grouped recap, then send one confirmation."""
    if pending.kind == "erase":
        return [await _erase(ctx, svc)]
    items = await _batch_items(ctx, pending) if pending.kind == "batch" else [pending]
    texts, receipts = [], []
    for item in items:
        applied = await actions.apply_pending(ctx, item)
        await queries.settle_pending(ctx.session, item, PendingStatus.CONFIRMED)
        texts.append(applied.reply.text)
        if applied.sale_entry_id:
            receipts.append(await _receipt_reply(ctx, svc, applied.sale_entry_id))
        if applied.extra:
            receipts.append(applied.extra)  # drawn with the other replies of this message
    if pending.kind == "batch":
        await queries.settle_pending(ctx.session, pending, PendingStatus.CONFIRMED)
    if not texts:
        return [Reply("Cette proposition a déjà été traitée.")]
    replies = [Reply(_one_confirmation(texts)), *receipts]
    if pending.payload.get("then_summary"):
        await ctx.session.flush()
        replies.append(await summary_reply(ctx.session, svc, ctx.shop, "today", ctx.now))
    return replies


async def _shop_card(session, svc: Services, shop: Shop) -> dict:
    """The header of every document: shop name, owner's number, logo if one was chosen."""
    owner = await queries.owner_of(session, shop.id)
    logo = None
    if shop.logo_key and svc.storage is not None:
        try:
            logo = await svc.storage.get(shop.logo_key)
        except Exception:
            log.exception("logo unavailable")
    return shop_card(shop, owner.whatsapp_id if owner else None, logo)


async def summary_reply(session, svc: Services, shop: Shop, period: str, now) -> Reply:
    """The summary as a ticket image with a one-line caption; the full text when there is nothing to
    draw or the image cannot be made."""
    figures = await actions.summary_figures(session, shop, period, now)
    if figures.empty:
        return Reply(actions.summary_text_of(figures))
    try:
        data = summary_data(await _shop_card(session, svc, shop), figures, now)
        png = await render_png("bilan.html.j2", data, summary_extra_height(data))
    except (RenderError, OSError):
        log.exception("summary rendering failed for shop %s", shop.id)
        return Reply(actions.summary_text_of(figures))
    return Reply(actions.summary_caption(figures), image=png)


async def _draw(ctx: Ctx, svc: Services, reply: Reply) -> Reply:
    """Draw the document a reply carries. If that fails, the reply goes out as its text alone."""
    kind, ref = reply.doc
    try:
        card = await _shop_card(ctx.session, svc, ctx.shop)
        template, data, extra = await DRAWERS[kind](ctx, card, ref)
        reply.image = await render_png(template, data, extra)
    except (RenderError, OSError):
        log.exception("could not draw %s %s", kind, ref)
        return reply
    if reply.caption:
        reply.text = reply.caption
    return reply


async def _receipt_number(session, entry_id: int) -> int | None:
    return (await session.exec(select(Receipt.number).where(Receipt.entry_id == entry_id))).first()


def _debt_label(e: Entry, left: int) -> str:
    if e.source == EntrySource.NOTEBOOK_PHOTO:
        return f"Cahier du {e.created_at:%d/%m}"
    return f"{'Reste de l’achat' if left < e.debt_delta else 'Achat'} du {e.created_at:%d/%m}"


REMINDER_ROWS = 7


async def _draw_reminder(ctx: Ctx, card: dict, contact_id: int):
    contact = await ctx.session.get(Contact, contact_id)
    entries = await ledger.contact_entries(ctx.session, shop_id=ctx.shop.id, contact_id=contact_id)
    items = []
    for e, left in ledger.open_items(entries):
        number = await _receipt_number(ctx.session, e.id)
        items.append({
            "label": _debt_label(e, left), "due": left, "date": f"{e.created_at:%d/%m/%Y}",
            "receipt": f"{number:04d}" if number else "",
        })  # fmt: skip
    if len(items) > REMINDER_ROWS:  # the oldest in one line, so the total stays right
        older, items = items[: -REMINDER_ROWS + 1], items[-REMINDER_ROWS + 1 :]
        items.insert(0, {"label": "Achats plus anciens", "due": sum(i["due"] for i in older),
                         "date": f"jusqu'au {older[-1]['date']}", "receipt": ""})  # fmt: skip
    return "rappel.html.j2", reminder_data(card, contact.name, items, ctx.now), max(len(items) - 3, 0) * 70


async def _draw_statement(ctx: Ctx, card: dict, contact_id: int):
    contact = await ctx.session.get(Contact, contact_id)
    entries = await ledger.contact_entries(ctx.session, shop_id=ctx.shop.id, contact_id=contact_id)
    operations = []
    for e in entries[-actions.STATEMENT_ROWS :]:
        if e.reverses_entry_id is not None:
            label = "Annulation"
        elif e.kind == EntryKind.PAYMENT_RECEIVED:
            label = "Paiement " + ("mobile money" if e.source == EntrySource.MOBILE_MONEY else "espèces")
        elif e.source == EntrySource.NOTEBOOK_PHOTO:
            label = "Repris du cahier"
        else:
            number = await _receipt_number(ctx.session, e.id)
            label = "Achat" + (f" · reçu {number:04d}" if number else "")
        operations.append({"date": f"{e.created_at:%d/%m}", "label": label, "delta": e.debt_delta})
    data = statement_data(card, contact.name, operations, sum(e.debt_delta for e in entries), ctx.now)
    return "releve.html.j2", data, max(len(operations) - 6, 0) * 50


async def _draw_settlement(ctx: Ctx, card: dict, entry_id: int):
    entry = await ctx.session.get(Entry, entry_id)
    contact = await ctx.session.get(Contact, entry.contact_id)
    after = await ledger.contact_balance(ctx.session, shop_id=ctx.shop.id, contact_id=contact.id)
    number = await _receipt_number(ctx.session, entry.id)
    if number is None:  # quittances share the receipts' numbering
        number = await queries.next_receipt_number(ctx.session, ctx.shop.id)
        ctx.session.add(Receipt(shop_id=ctx.shop.id, entry_id=entry.id, number=number, image_key=""))
        await ctx.session.flush()
    data = settlement_data(card, number, contact.name, after + entry.amount, entry, ctx.now)
    return "quittance.html.j2", data, 0


async def _draw_stock(ctx: Ctx, card: dict, _: int):
    products = await queries.tracked_products(ctx.session, ctx.shop.id)
    sold = await queries.quantities_sold(ctx.session, ctx.shop.id, ctx.now - timedelta(days=7))
    data = stock_data(card, products, sold, queries.product_key, ctx.now, actions.LOW_STOCK)
    return "stock.html.j2", data, max(len(data["products"]) - 6, 0) * 70


DRAWERS = {
    "rappel": _draw_reminder,
    "releve": _draw_statement,
    "quittance": _draw_settlement,
    "stock": _draw_stock,
}


async def _demo_receipt(ctx: Ctx, svc: Services) -> Reply:
    """The receipt of the onboarding's example sale, in the merchant's name. Nothing is written: the
    entry only exists to be drawn, and the receipt is marked as an example."""
    d = DEMO_SALE
    total = d["quantity"] * d["unit_price"]
    line = {"product": d["product"], "quantity": d["quantity"], "unit": None, "unit_price": d["unit_price"],
            "total": total}  # fmt: skip
    entry = Entry(id=0, shop_id=ctx.shop.id, kind=EntryKind.SALE, amount=total, debt_delta=total - d["paid"],
                  lines=[line])  # fmt: skip
    try:
        data = receipt_data(await _shop_card(ctx.session, svc, ctx.shop), entry, 0, d["customer"], ctx.now)
        data.update(number="EXEMPLE", code="exemple, rien n'est noté")
        png = await render_png("recu_ticket.html.j2", data, extra_height(1))
    except (RenderError, OSError):
        log.exception("demo receipt rendering failed for shop %s", ctx.shop.id)
        return Reply("Je n'ai pas pu dessiner le reçu d'exemple, mais tout est prêt pour une vraie vente.")
    return Reply(f"Reçu pour {d['customer']}", image=png)


async def _receipt_reply(ctx: Ctx, svc: Services, entry_id: int) -> Reply:
    """The receipt image for a sale. A rendering failure never undoes the sale."""
    entry = await ctx.session.get(Entry, entry_id)
    try:
        card = await _shop_card(ctx.session, svc, ctx.shop)
        existing = (await ctx.session.exec(select(Receipt).where(Receipt.entry_id == entry.id))).first()
        number = existing.number if existing else await queries.next_receipt_number(ctx.session, ctx.shop.id)
        customer = ""
        if entry.contact_id:
            from app.db.models import Contact

            contact = await ctx.session.get(Contact, entry.contact_id)
            customer = contact.name if contact else ""
        data = receipt_data(card, entry, number, customer, ctx.now)
        png = await render_png("recu_ticket.html.j2", data, extra_height(len(entry.lines)))
        key = ""
        if svc.storage is not None:
            key = media_key(ctx.shop.id, "receipt", "image/png")
            await svc.storage.put(key, png, "image/png")
        if existing is None:
            ctx.session.add(Receipt(shop_id=ctx.shop.id, entry_id=entry.id, number=number, image_key=key))
        who = f" pour {customer}" if customer else ""
        return Reply(f"Reçu n° {number:04d}{who}. Transférez-le à votre client ↗", image=png)
    except (RenderError, OSError):
        log.exception("receipt rendering failed for entry %s", entry_id)
        return Reply("Je n'ai pas pu préparer l'image du reçu, mais la vente est bien notée.")
