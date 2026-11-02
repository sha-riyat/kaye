"""Scheduled jobs: the evening summary and supplier due-date reminders.

Outside the 24 h window after the merchant's last message, WhatsApp only accepts approved
templates. We try a free message first and fall back to the template named in settings.
"""

import logging
from datetime import timedelta

from app.agent import actions
from app.agent.reply import Reply
from app.db import ledger, queries
from app.db.models import AppUser, Shop
from app.router import summary_reply
from app.services import Services
from app.whatsapp import WhatsAppError

log = logging.getLogger(__name__)

SUPPLIER_REMINDER_HOUR = 8
REENGAGEMENT_ERROR = "131047"  # more than 24 h since the merchant's last message


async def run_hourly(svc: Services) -> None:
    now = queries.utcnow()  # Africa/Lome is UTC all year
    async with svc.db.session() as session:
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


async def _evening_summary(svc: Services, session, shop: Shop, owner: AppUser, now) -> None:
    start, end = queries.day_bounds(now)
    today = await ledger.period_summary(session, shop_id=shop.id, start=start, end=end)
    owed = sum(d.balance for d in await ledger.debtors(session, shop_id=shop.id))
    if today.operations == 0 and owed == 0:
        return
    reply = await summary_reply(session, svc, shop, "today", now)
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
    await _send(svc, owner.whatsapp_id, Reply("*Rappel fournisseurs*\n" + "\n".join(lines)), template_params=None)


async def _send(svc: Services, to: str, reply: Reply, template_params: list[str] | None) -> None:
    try:
        await svc.wa.deliver(to, reply)
    except WhatsAppError as exc:
        template = svc.settings.summary_template_name
        if REENGAGEMENT_ERROR in str(exc) and template and template_params:
            await svc.wa.send_template(to, template, template_params)
        else:
            log.warning("could not reach %s: %s", to, exc)
