"""Scheduled jobs: the evening summary, supplier due-date reminders, and one nudge to newcomers.

Outside the 24 h window after the merchant's last message, WhatsApp only accepts approved
templates. We try a free message first and fall back to the template named in settings.
"""

import logging
from datetime import timedelta

from app import language
from app.agent import actions
from app.agent.prompts import NUDGE_FIRST, NUDGE_NAME
from app.agent.reply import Reply
from app.db import ledger, queries
from app.db.models import AppUser, PendingStatus, Shop
from app.router import START_BUTTONS, name_buttons, summary_reply
from app.services import Services
from app.whatsapp import WhatsAppError

log = logging.getLogger(__name__)

SUPPLIER_REMINDER_HOUR = 8
REENGAGEMENT_ERROR = "131047"  # more than 24 h since the merchant's last message
# A newcomer silent for an hour gets one nudge; never after 23 h, so it stays a free in-window message.
NUDGE_AFTER, NUDGE_UNTIL = timedelta(hours=1), timedelta(hours=23)


async def run_hourly(svc: Services) -> None:
    now = queries.utcnow()  # Africa/Lome is UTC all year
    async with svc.db.session() as session:
        for owner in await queries.new_owners(session, now - NUDGE_UNTIL, now - NUDGE_AFTER):
            try:
                await _nudge(svc, session, owner)
            except Exception:
                log.exception("nudge failed for shop %s", owner.shop_id)
        for shop in await queries.all_shops(session):
            owner = await queries.owner_of(session, shop.id)
            if owner is None:
                continue
            try:
                if shop.summary_hour == now.hour:
                    await _evening_summary(svc, session, shop, owner, now)
                if now.hour == SUPPLIER_REMINDER_HOUR:
                    await _supplier_reminders(svc, session, shop, owner, now)
            except Exception:
                log.exception("job failed for shop %s", shop.id)


async def _nudge(svc: Services, session, owner: AppUser) -> None:
    """One message, once, to a newcomer who stopped before naming the business or before the first
    operation. Someone who has not even picked a language is left alone."""
    shop = await session.get(Shop, owner.shop_id)
    if shop is None or shop.language is None or await queries.was_nudged(session, shop.id):
        return
    if not shop.name:
        reply = Reply(NUDGE_NAME, buttons=name_buttons(owner.name))
    elif not await queries.has_entries(session, shop.id):
        said = await queries.last_said_at(session, owner.id)
        if said is not None and queries.utcnow() - said < NUDGE_AFTER:
            return  # in the middle of a conversation: no nudge on top of it
        reply = Reply(NUDGE_FIRST, buttons=list(START_BUTTONS))
    else:
        return
    marker = await queries.create_pending(session, shop_id=shop.id, user_id=owner.id, kind="nudge", payload={},
                                          wamid=None)  # fmt: skip
    await queries.settle_pending(session, marker, PendingStatus.CONFIRMED)  # a record, never a proposal
    [reply] = await language.localize(svc.agent.models, session, shop.id, shop.language, [reply])
    try:
        await svc.wa.deliver(owner.whatsapp_id, reply)
    except WhatsAppError as exc:
        log.warning("could not nudge %s: %s", owner.whatsapp_id, exc)  # no template: a nudge is never forced


async def _evening_summary(svc: Services, session, shop: Shop, owner: AppUser, now) -> None:
    start, end = queries.day_bounds(now)
    today = await ledger.period_summary(session, shop_id=shop.id, start=start, end=end)
    owed = sum(d.balance for d in await ledger.debtors(session, shop_id=shop.id))
    if today.operations == 0 and owed == 0:
        return
    reply = await summary_reply(session, svc, shop, "today", now)
    [reply] = await language.localize(svc.agent.models, session, shop.id, shop.language, [reply])
    short = f"ventes {actions.money(today.sales)} FCFA, à encaisser {actions.money(owed)} FCFA"
    await _send(svc, owner.whatsapp_id, reply, template_params=[shop.name, short])


async def _supplier_reminders(svc: Services, session, shop: Shop, owner: AppUser, now) -> None:
    horizon = (now + timedelta(days=1)).date()
    due = [d for d in await ledger.supplier_dues(session, shop_id=shop.id) if d.due_date and d.due_date <= horizon]
    if not due:
        return
    lines = []
    for d in due:
        when = "aujourd'hui" if d.due_date <= now.date() else "demain"
        lines.append(f"• {d.contact.name} : {actions.money(d.balance)} FCFA, à payer {when}")
    reply = Reply("*Rappel fournisseurs*\n" + "\n".join(lines))
    [reply] = await language.localize(svc.agent.models, session, shop.id, shop.language, [reply])
    await _send(svc, owner.whatsapp_id, reply, template_params=None)


async def _send(svc: Services, to: str, reply: Reply, template_params: list[str] | None) -> None:
    try:
        await svc.wa.deliver(to, reply)
    except WhatsAppError as exc:
        template = svc.settings.summary_template_name
        if REENGAGEMENT_ERROR in str(exc) and template and template_params:
            await svc.wa.send_template(to, template, template_params)
        else:
            log.warning("could not reach %s: %s", to, exc)
