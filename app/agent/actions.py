"""The agent's tools, implemented in code.

The model only picks a tool and fills its arguments. Here the code resolves names, recomputes every
amount, writes the confirmation text, and — once the merchant taps "Oui" — applies the write.
Reads answer directly, with no second model call.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from urllib.parse import quote

from pydantic import BaseModel, ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.agent import schemas as s
from app.agent.reply import Reply, confirm_buttons
from app.db import ledger, queries
from app.db.ledger import LedgerError, Line
from app.db.models import (
    AppUser,
    Contact,
    ContactKind,
    EntryKind,
    EntrySource,
    PendingAction,
    PendingStatus,
    Shop,
)
from app.documents.render import fcfa

log = logging.getLogger(__name__)

LOW_STOCK = 3
MAX_LIST_ROWS = 10


@dataclass
class Ctx:
    session: AsyncSession
    shop: Shop
    user: AppUser
    wamid: str | None = None
    source: str = EntrySource.TEXT
    media_id: int | None = None
    text: str = ""  # what the merchant said (or the voice transcript)
    replaying: bool = False  # this message answers our question: its other operations were proposed already
    now: datetime = field(default_factory=queries.utcnow)


@dataclass
class Applied:
    """Result of confirming a pending action."""

    reply: Reply
    sale_entry_id: int | None = None  # a receipt should follow


def money(amount: int) -> str:
    return fcfa(amount)


# --- argument validation ---

WRITE_TOOLS: dict[str, type[BaseModel]] = {
    "propose_sale": s.ProposeSale,
    "propose_payment": s.ProposePayment,
    "propose_supplier_debt": s.ProposeSupplierDebt,
    "propose_supplier_payment": s.ProposeSupplierPayment,
    "propose_expense": s.ProposeExpense,
    "propose_stock_change": s.ProposeStockChange,
    "propose_correction": s.NoArgs,
    "add_seller": s.AddSeller,
    "notebook_page": s.NotebookPage,
    "mobile_money_receipt": s.MobileMoneyReceipt,
}
READ_TOOLS: dict[str, type[BaseModel]] = {
    "customer_balance": s.CustomerName,
    "list_debtors": s.NoArgs,
    "list_supplier_dues": s.NoArgs,
    "summary": s.SummaryRequest,
    "stock_levels": s.StockQuestion,
    "draft_reminder": s.CustomerName,
}
TOOL_MODELS = {**WRITE_TOOLS, **READ_TOOLS}

SELLER_TOOLS = {"propose_sale", "stock_levels"}
SELLER_REFUSAL = "Cette demande est réservée au patron de la boutique. Vous pouvez noter vos ventes."

REPHRASE = "Je n'ai pas bien compris. Pouvez-vous le redire plus simplement, avec le nom et le montant ?"


async def run_tool(ctx: Ctx, name: str, arguments: str) -> list[Reply]:
    model = TOOL_MODELS.get(name)
    if model is None:
        return [Reply(REPHRASE)]
    try:
        args = model.model_validate_json(arguments or "{}")
    except ValidationError:
        log.warning("invalid arguments for %s: %s", name, arguments)
        return [Reply(REPHRASE)]
    if ctx.user.role != "owner" and name not in SELLER_TOOLS:
        return [Reply(SELLER_REFUSAL)]
    handler = HANDLERS[name]
    return await handler(ctx, args)


# --- parties (customers and suppliers) ---


async def _resolve_party(ctx: Ctx, spoken: str | None, kind: ContactKind) -> dict:
    """Who is this? One match -> use it. None -> a new contact on confirmation. Several -> ask."""
    if not spoken or not spoken.strip():
        return {"id": None, "name": "", "new": False, "spoken": "", "candidates": []}
    matches, confident = await queries.match_contacts(ctx.session, ctx.shop.id, spoken, kind)
    if confident and len(matches) == 1:
        c = matches[0]
        return {"id": c.id, "name": c.name, "new": False, "spoken": spoken, "candidates": []}
    if not matches:
        return {"id": None, "name": spoken.strip(), "new": True, "spoken": spoken, "candidates": []}
    return {
        "id": None,
        "name": spoken.strip(),
        "new": False,
        "spoken": spoken,
        "candidates": [{"id": m.id, "name": m.name} for m in matches[: MAX_LIST_ROWS - 1]],
    }


def _ask_which(pending_id: int, party: dict, noun: str) -> Reply:
    rows = [(f"pick:{pending_id}:{c['id']}", c["name"][:24], "") for c in party["candidates"]]
    rows.append((f"pick:{pending_id}:new", f"Nouveau : {party['name']}"[:24], ""))
    text = f"J'ai plusieurs {noun} qui ressemblent à « {party['spoken']} ». Lequel ?"
    if len(rows) <= 3:
        return Reply(text, buttons=[(rid, title[:20]) for rid, title, _ in rows], kind="choice")
    return Reply(text, rows=rows, list_button="Choisir", kind="choice")


async def _party_contact(ctx: Ctx, party: dict, kind: ContactKind) -> Contact:
    """The contact for a confirmed party, created now if it was new."""
    if party["id"]:
        contact = await ctx.session.get(Contact, party["id"])
        if contact is None or contact.shop_id != ctx.shop.id:
            raise LedgerError("contact not found")
    else:
        contact = await queries.create_contact(ctx.session, ctx.shop.id, party["name"], kind)
    if party.get("spoken"):
        await queries.remember_alias(ctx.session, contact, party["spoken"])
    return contact


async def _propose(ctx: Ctx, kind: str, payload: dict, party: dict | None = None, noun: str = "clients") -> list[Reply]:
    if ctx.replaying and await queries.recent_same_proposal(ctx.session, ctx.user.id, kind, payload):
        return []  # proposed with the first message; only the answered operation is new
    pending = await queries.create_pending(
        ctx.session, shop_id=ctx.shop.id, user_id=ctx.user.id, kind=kind, payload=payload, wamid=ctx.wamid
    )
    if party and party["candidates"] and not party["id"]:
        return [_ask_which(pending.id, party, noun)]
    return [Reply(describe(pending), buttons=confirm_buttons(pending.id), kind="proposal")]


async def _clarify(ctx: Ctx, question: str, original: str | None) -> list[Reply]:
    """Ask a question and remember the original message, so the answer can be read in context."""
    if original:
        await queries.create_pending(
            ctx.session, shop_id=ctx.shop.id, user_id=ctx.user.id, kind="clarify",
            payload={"original": original, "question": question}, wamid=ctx.wamid,
        )  # fmt: skip
    return [Reply(question, kind="question")]


# --- one recap per message ---

ASK = "\n\nJe note ?"


def _body(text: str) -> str:
    return text.removesuffix(ASK)


async def merge(ctx: Ctx, replies: list[Reply]) -> list[Reply]:
    """Fold everything a message produced into one recap with one set of buttons.

    A voice note often holds several operations (a sale, a delivery, an expense): the merchant
    gets a single summary to confirm, and any missing price or amount is asked at its bottom.
    """
    proposals = [r for r in replies if r.kind == "proposal"]
    questions = [r for r in replies if r.kind == "question"]
    others = [r for r in replies if r.kind not in ("proposal", "question")]
    missing = "\n".join(f"❓ {q.text}" for q in questions)

    if not proposals:
        return others + (
            [Reply(missing.replace("❓ ", "") if len(questions) == 1 else missing, kind="question")]
            if questions
            else []
        )

    if len(proposals) == 1:
        recap, pending_id = _body(proposals[0].text), int(proposals[0].buttons[0][0].split(":")[1])
    else:
        ids = [int(p.buttons[0][0].split(":")[1]) for p in proposals]
        recap = "\n\n".join(_body(p.text) for p in proposals)
        batch = await queries.create_pending(
            ctx.session, shop_id=ctx.shop.id, user_id=ctx.user.id, kind="batch",
            payload={"ids": ids, "text": recap}, wamid=ctx.wamid,
        )  # fmt: skip
        pending_id = batch.id
    if missing:
        recap += f"\n\n{missing}\n_Répondez quand vous voulez. Le reste peut être noté tout de suite._"
    ask = "\n\nJe note ?" if len(proposals) == 1 else "\n\nJe note tout ?"
    return others + [Reply(recap + ask, buttons=confirm_buttons(pending_id), kind="proposal")]


# --- confirmation text, always built by code ---


def plural(unit: str, quantity: int) -> str:
    """'sac' -> 'sacs' when more than one; units already ending in s or x stay as they are."""
    if quantity > 1 and " " not in unit and not unit.endswith(("s", "x")):
        return unit + "s"
    return unit


def _qty(line: dict) -> str:
    unit = line.get("unit")
    return f"{line['quantity']} {plural(unit, line['quantity'])}" if unit else f"{line['quantity']}"


def _who(party: dict) -> str:
    return party["name"] + (" _(nouveau)_" if party.get("new") else "")


def describe(pending: PendingAction) -> str:
    p, kind = pending.payload, pending.kind
    if kind == "batch":
        return p["text"]
    if kind == "sale":
        lines = "\n".join(
            f"{_qty(ln)} {ln['product']} × {money(ln['unit_price'])} = {money(ln['total'])}" for ln in p["lines"]
        )
        who = f" à {_who(p['party'])}" if p["party"]["name"] else ""
        out = f"*Vente{who}*\n{lines}\nTotal : *{money(p['total'])} FCFA*"
        if p["paid"] < p["total"]:
            out += f"\nPayé : {money(p['paid'])} · Reste dû : *{money(p['total'] - p['paid'])}*"
        elif p["party"]["name"]:
            out += "\nPayé en totalité"
        if p.get("warning"):
            out += f"\n⚠️ {p['warning']}"
        return out + "\n\nJe note ?"
    if kind == "payment":
        out = f"*Paiement de {_who(p['party'])}*\n{money(p['amount'])} FCFA reçus"
        if p.get("provider"):
            out += f" par {p['provider']}"
        if p.get("balance_before") is not None:
            after = p["balance_before"] - p["amount"]
            out += f"\nDette : {money(p['balance_before'])} → *{money(max(after, 0))}*"
            if after < 0:
                out += f"\n⚠️ C'est {money(-after)} de plus que la dette."
        return out + "\n\nJe note ?"
    if kind == "supplier_debt":
        out = f"*Achat chez {_who(p['party'])}*"
        if p.get("items"):
            out += f"\n{p['items']}"
        out += f"\nTotal : *{money(p['amount'])} FCFA*"
        if p["paid"]:
            out += f"\nPayé : {money(p['paid'])}"
        if p["amount"] - p["paid"] > 0:
            out += f"\nÀ payer : *{money(p['amount'] - p['paid'])}*"
            if p.get("due_date"):
                out += f" avant le {date.fromisoformat(p['due_date']):%d/%m/%Y}"
        return out + "\n\nJe note ?"
    if kind == "supplier_payment":
        return f"*Paiement à {_who(p['party'])}*\n{money(p['amount'])} FCFA payés\n\nJe note ?"
    if kind == "expense":
        return f"*Dépense : {p['label']}*\n{money(p['amount'])} FCFA\n\nJe note ?"
    if kind == "stock":
        verb = {"add": "Entrée", "remove": "Sortie", "set": "Recomptage"}[p["mode"]]
        unit = f" {p['unit']}" if p.get("unit") else ""
        out = f"*{verb} de stock : {p['product']}*\n{p['quantity']}{unit}"
        out += f"\nStock : {p['before']} → *{p['after']}*"
        return out + "\n\nJe note ?"
    if kind == "seller":
        who = p.get("name") or f"+{p['phone']}"
        return (
            f"*Ajouter {who} comme vendeur*\nIl pourra noter des ventes, "
            "sans voir les totaux ni les dettes.\n\nJe l'ajoute ?"
        )
    if kind == "correction":
        return f"*Annuler cette opération ?*\n{p['label']}\n\nElle sera annulée, sans rien effacer du cahier."
    if kind == "import":
        shown = p["lines"][:25]
        rows = "\n".join(
            f"{'❓ ' if ln['unclear'] else ''}{ln['customer']} : {money(ln['amount_owed'])}"
            + (f" ({ln['description']})" if ln.get("description") else "")
            for ln in shown
        )
        more = f"\n… et {len(p['lines']) - len(shown)} autres" if len(p["lines"]) > len(shown) else ""
        total = sum(ln["amount_owed"] for ln in p["lines"])
        flagged = sum(1 for ln in p["lines"] if ln["unclear"])
        note = f"\n❓ {flagged} ligne(s) à vérifier : l'écriture n'était pas claire." if flagged else ""
        return (
            f"*J'ai lu {len(p['lines'])} dette(s) dans votre cahier*\n{rows}{more}\n"
            f"Total : *{money(total)} FCFA*{note}\n\nJe les note toutes ?"
        )
    return "Je note ?"


# --- write tools: build proposals ---


async def propose_sale(ctx: Ctx, a: s.ProposeSale) -> list[Reply]:
    lines: list[dict] = []
    for ln in a.lines:
        price = ln.unit_price
        if price is None and a.total and len(a.lines) == 1 and a.total % ln.quantity == 0:
            price = a.total // ln.quantity
        if price is None:
            price = await queries.usual_price(ctx.session, ctx.shop.id, ln.product, ln.unit)
        if price is None:
            each = f"pour 1 {ln.unit} de {ln.product}" if ln.unit else f"de {ln.product}, à l'unité"
            return await _clarify(ctx, f"Quel est le prix {each} ?", _original(ctx, a))
        lines.append(
            {
                "product": ln.product,
                "quantity": ln.quantity,
                "unit": ln.unit,
                "unit_price": price,
                "total": ln.quantity * price,
            }
        )
    total = sum(ln["total"] for ln in lines)
    warning = None
    if a.total is not None and a.total != total:
        warning = f"Vous avez dit {money(a.total)} mais le calcul donne {money(total)}."
    if a.paid is not None:
        paid = min(a.paid, total)
    elif a.remaining_debt is not None:
        paid = max(total - a.remaining_debt, 0)
    else:
        paid = total
    party = await _resolve_party(ctx, a.customer, ContactKind.CUSTOMER)
    if paid < total and not party["name"]:
        return await _clarify(ctx, "Cette vente reste en partie à payer : pour quel client ?", _original(ctx, a))
    payload = {"party": party, "lines": lines, "total": total, "paid": paid, "warning": warning}
    return await _propose(ctx, "sale", payload, party)


def _original(ctx: Ctx, a: BaseModel) -> str:
    """The merchant's own words, replayed to the model together with the answer to our question."""
    return f"Message du commerçant : {ctx.text}" if ctx.text else "Propose " + a.model_dump_json(exclude_none=True)


async def propose_payment(ctx: Ctx, a: s.ProposePayment, *, provider: str | None = None,
                          reference: str | None = None, source: str | None = None) -> list[Reply]:  # fmt: skip
    party = await _resolve_party(ctx, a.customer, ContactKind.CUSTOMER)
    balance = None
    if party["id"]:
        balance = await ledger.contact_balance(ctx.session, shop_id=ctx.shop.id, contact_id=party["id"])
    payload = {
        "party": party, "amount": a.amount, "provider": provider, "reference": reference,
        "balance_before": balance, "source": source or ctx.source,
    }  # fmt: skip
    return await _propose(ctx, "payment", payload, party)


async def propose_supplier_debt(ctx: Ctx, a: s.ProposeSupplierDebt) -> list[Reply]:
    if a.amount is None:
        what = f" pour {a.items}" if a.items else ""
        return await _clarify(ctx, f"Combien devez-vous à {a.supplier}{what} ?", _original(ctx, a))
    party = await _resolve_party(ctx, a.supplier, ContactKind.SUPPLIER)
    due = None
    if a.due_date:
        try:
            due = date.fromisoformat(a.due_date).isoformat()
        except ValueError:
            due = None
    paid = min(a.paid or 0, a.amount)
    payload = {"party": party, "amount": a.amount, "paid": paid, "due_date": due, "items": a.items}
    return await _propose(ctx, "supplier_debt", payload, party, noun="fournisseurs")


async def propose_supplier_payment(ctx: Ctx, a: s.ProposeSupplierPayment) -> list[Reply]:
    party = await _resolve_party(ctx, a.supplier, ContactKind.SUPPLIER)
    return await _propose(ctx, "supplier_payment", {"party": party, "amount": a.amount}, party, noun="fournisseurs")


async def propose_expense(ctx: Ctx, a: s.ProposeExpense) -> list[Reply]:
    return await _propose(ctx, "expense", {"amount": a.amount, "label": a.label.strip()})


async def propose_stock_change(ctx: Ctx, a: s.ProposeStockChange) -> list[Reply]:
    mode = a.mode if a.mode in ("add", "remove", "set") else "add"
    product = await queries.get_product(ctx.session, ctx.shop.id, a.product)
    before = (product.stock or 0) if product else 0
    after = {"add": before + a.quantity, "remove": before - a.quantity, "set": a.quantity}[mode]
    payload = {"product": product.name if product else a.product.strip().lower(), "quantity": a.quantity,
               "mode": mode, "unit": a.unit, "before": before, "after": after}  # fmt: skip
    return await _propose(ctx, "stock", payload)


async def add_seller(ctx: Ctx, a: s.AddSeller) -> list[Reply]:
    digits = "".join(ch for ch in a.phone if ch.isdigit())
    if len(digits) < 8:
        return [Reply("Je n'ai pas bien lu le numéro. Donnez-le avec l'indicatif, par exemple +228 90 12 34 56.")]
    if await queries.user_by_whatsapp(ctx.session, digits):
        return [Reply("Ce numéro utilise déjà Kayé.")]
    return await _propose(ctx, "seller", {"phone": digits, "name": a.name})


async def propose_correction(ctx: Ctx, _: s.NoArgs) -> list[Reply]:
    last = await ledger.last_active_entry(
        ctx.session, shop_id=ctx.shop.id, created_by=None if ctx.user.role == "owner" else ctx.user.id
    )
    if last is None:
        return [Reply("Il n'y a rien à annuler pour le moment.")]
    label = await _entry_label(ctx, last)
    return await _propose(ctx, "correction", {"entry_id": last.id, "label": label})


async def _entry_label(ctx: Ctx, entry) -> str:
    who = ""
    if entry.contact_id:
        c = await ctx.session.get(Contact, entry.contact_id)
        who = f" · {c.name}" if c else ""
    names = {
        "sale": "Vente", "payment_received": "Paiement reçu", "supplier_purchase": "Achat fournisseur",
        "supplier_payment": "Paiement fournisseur", "expense": "Dépense",
    }  # fmt: skip
    return f"{names.get(entry.kind, entry.kind)}{who} · {money(entry.amount)} FCFA · {entry.created_at:%d/%m %H:%M}"


async def notebook_page(ctx: Ctx, a: s.NotebookPage) -> list[Reply]:
    lines = [ln.model_dump() for ln in a.lines if ln.amount_owed > 0]
    if not lines:
        return [Reply("Je n'ai trouvé aucune dette sur cette photo. Essayez avec une page plus nette, bien à plat.")]
    return await _propose(ctx, "import", {"lines": lines, "media_id": ctx.media_id})


async def mobile_money_receipt(ctx: Ctx, a: s.MobileMoneyReceipt) -> list[Reply]:
    if a.reference and await _reference_seen(ctx, a.reference):
        return [Reply(f"Ce paiement ({a.reference}) est déjà noté. Je ne le compte pas deux fois.")]
    contact = await queries.contact_by_phone(ctx.session, ctx.shop.id, a.sender_phone) if a.sender_phone else None
    name = contact.name if contact else a.sender_name
    if not name:
        return [
            Reply(
                f"J'ai lu {money(a.amount)} FCFA reçus par {a.provider}, mais je ne vois pas de qui. De quel client ?"
            )
        ]
    args = s.ProposePayment(customer=name, amount=a.amount)
    return await propose_payment(ctx, args, provider=a.provider, reference=a.reference, source=EntrySource.MOBILE_MONEY)


async def _reference_seen(ctx: Ctx, reference: str) -> bool:
    from sqlmodel import select

    from app.db.models import Entry

    found = await ctx.session.exec(
        select(Entry.id).where(Entry.shop_id == ctx.shop.id, Entry.payment_reference == reference)
    )
    return found.first() is not None


# --- read tools: answered by code ---


async def customer_balance(ctx: Ctx, a: s.CustomerName) -> list[Reply]:
    matches = await queries.find_contacts(ctx.session, ctx.shop.id, a.name)
    if not matches:
        return [Reply(f"Je ne connais pas « {a.name} » dans votre cahier.")]
    if len(matches) > 1:
        names = ", ".join(m.name for m in matches[:5])
        return [Reply(f"Plusieurs contacts ressemblent à « {a.name} » : {names}. Lequel ?")]
    c = matches[0]
    balance = await ledger.contact_balance(ctx.session, shop_id=ctx.shop.id, contact_id=c.id)
    if c.kind == ContactKind.SUPPLIER:
        text = f"Vous devez *{money(balance)} FCFA* à {c.name}." if balance > 0 else f"Vous ne devez rien à {c.name}."
        return [Reply(text)]
    if balance <= 0:
        return [
            Reply(f"{c.name} ne vous doit rien." + (f" Vous lui devez {money(-balance)} FCFA." if balance < 0 else ""))
        ]
    return [Reply(f"{c.name} vous doit *{money(balance)} FCFA*.", buttons=[(f"rem:{c.id}", "Préparer la relance")])]


async def list_debtors(ctx: Ctx, _: s.NoArgs | None = None) -> list[Reply]:
    rows = await ledger.debtors(ctx.session, shop_id=ctx.shop.id)
    if not rows:
        return [Reply("Personne ne vous doit rien. 🎉")]
    lines = []
    for d in rows[:15]:
        since = f" · depuis {d.oldest_credit_at:%d/%m}" if d.oldest_credit_at else ""
        lines.append(f"{d.contact.name} : *{money(d.balance)}*{since}")
    total = sum(d.balance for d in rows)
    text = "*Ils vous doivent :*\n" + "\n".join(lines) + f"\n\nTotal : *{money(total)} FCFA*"
    buttons = [(f"rem:{d.contact.id}", f"Relancer {d.contact.name.split()[0]}"[:20]) for d in rows[:3]]
    return [Reply(text, buttons=buttons)]


async def list_supplier_dues(ctx: Ctx, _: s.NoArgs | None = None) -> list[Reply]:
    rows = await ledger.supplier_dues(ctx.session, shop_id=ctx.shop.id)
    if not rows:
        return [Reply("Vous ne devez rien à vos fournisseurs.")]
    lines = []
    for r in rows:
        due = f" · avant le {r.due_date:%d/%m}" if r.due_date else ""
        lines.append(f"{r.contact.name} : *{money(r.balance)}*{due}")
    total = sum(r.balance for r in rows)
    return [Reply("*Vous devez :*\n" + "\n".join(lines) + f"\n\nTotal : *{money(total)} FCFA*")]


def period_bounds(period: str, now: datetime) -> tuple[datetime, datetime, str]:
    start, end = queries.day_bounds(now)
    if period == "yesterday":
        return start - timedelta(days=1), start, "d'hier"
    if period == "week":
        return end - timedelta(days=7), end, "des 7 derniers jours"
    if period == "month":
        return end - timedelta(days=30), end, "des 30 derniers jours"
    return start, end, "du jour"


async def summary(ctx: Ctx, a: s.SummaryRequest) -> list[Reply]:
    return [Reply(await summary_text(ctx.session, ctx.shop, a.period, ctx.now))]


async def summary_text(session: AsyncSession, shop: Shop, period: str, now: datetime | None = None) -> str:
    start, end, label = period_bounds(period, now or queries.utcnow())
    p = await ledger.period_summary(session, shop_id=shop.id, start=start, end=end)
    debtors = await ledger.debtors(session, shop_id=shop.id)
    owed = sum(d.balance for d in debtors)
    out = [f"*Bilan {label}*"]
    if p.operations == 0:
        out.append("Aucune opération notée.")
    else:
        out += [
            f"Ventes : *{money(p.sales)} FCFA*",
            f"  encaissé {money(p.cashed)} · à crédit {money(p.credit)}",
        ]
        if p.mobile_money:
            out.append(f"  dont mobile money {money(p.mobile_money)}")
        if p.repaid:
            out.append(f"Dettes remboursées : {money(p.repaid)}")
        if p.expenses or p.supplier_paid:
            out.append(f"Sorties : {money(p.expenses + p.supplier_paid)}")
        out.append(f"En caisse : *{money(p.cash_in_hand)} FCFA*")
    if owed:
        out.append(f"\nÀ encaisser : *{money(owed)} FCFA* ({len(debtors)} client(s))")
    low = [pr for pr in await queries.tracked_products(session, shop.id) if (pr.stock or 0) <= LOW_STOCK]
    if low:
        out.append("Stock bas : " + ", ".join(f"{pr.name} ({pr.stock})" for pr in low[:5]))
    return "\n".join(out)


async def stock_levels(ctx: Ctx, a: s.StockQuestion) -> list[Reply]:
    if a.product:
        p = await queries.get_product(ctx.session, ctx.shop.id, a.product)
        if p is None or p.stock is None:
            return [
                Reply(
                    f"Je ne suis pas encore le stock de « {a.product} ». "
                    "Dites-moi combien vous en avez : « j'ai 20 sacs de riz »."
                )
            ]
        unit = f" {p.default_unit}" if p.default_unit else ""
        return [Reply(f"Il reste *{p.stock}{unit}* de {p.name}.")]
    products = await queries.tracked_products(ctx.session, ctx.shop.id)
    if not products:
        return [Reply("Je ne suis encore aucun stock. Dites-moi par exemple : « j'ai reçu 20 sacs de riz ».")]
    lines = [f"{'⚠️ ' if (p.stock or 0) <= LOW_STOCK else ''}{p.name} : *{p.stock}*" for p in products[:30]]
    return [Reply("*Votre stock :*\n" + "\n".join(lines))]


async def draft_reminder(ctx: Ctx, a: s.CustomerName) -> list[Reply]:
    matches = await queries.find_contacts(ctx.session, ctx.shop.id, a.name, ContactKind.CUSTOMER)
    if len(matches) != 1:
        return [Reply(f"Quel client voulez-vous relancer ? Je ne trouve pas « {a.name} » avec certitude.")]
    return [await reminder_for(ctx, matches[0])]


async def reminder_for(ctx: Ctx, c: Contact) -> Reply:
    balance = await ledger.contact_balance(ctx.session, shop_id=ctx.shop.id, contact_id=c.id)
    if balance <= 0:
        return Reply(f"{c.name} ne vous doit rien.")
    first = c.name.split()[0]
    message = f"Bonjour {first}, il reste {money(balance)} FCFA chez {ctx.shop.name}. Passez quand vous pouvez, merci !"
    link = None
    if c.phone:
        digits = "".join(ch for ch in c.phone if ch.isdigit())
        link = f"https://wa.me/{digits}?text={quote(message)}"
    intro = "Voici le message prêt à envoyer :" if link else "Voici le message à envoyer (pas de numéro enregistré) :"
    return Reply(f"{intro}\n\n{message}", link=link)


HANDLERS = {
    "propose_sale": propose_sale,
    "propose_payment": propose_payment,
    "propose_supplier_debt": propose_supplier_debt,
    "propose_supplier_payment": propose_supplier_payment,
    "propose_expense": propose_expense,
    "propose_stock_change": propose_stock_change,
    "propose_correction": propose_correction,
    "add_seller": add_seller,
    "notebook_page": notebook_page,
    "mobile_money_receipt": mobile_money_receipt,
    "customer_balance": customer_balance,
    "list_debtors": list_debtors,
    "list_supplier_dues": list_supplier_dues,
    "summary": summary,
    "stock_levels": stock_levels,
    "draft_reminder": draft_reminder,
}


# --- confirming a pending action ---


async def apply_pending(ctx: Ctx, pending: PendingAction) -> Applied:
    """Write the ledger entries for a confirmed proposal. Called only after a tap on "Oui"."""
    p, kind = pending.payload, pending.kind
    sid, uid = ctx.shop.id, ctx.user.id
    try:
        if kind == "sale":
            return await _apply_sale(ctx, p)
        if kind == "payment":
            contact = await _party_contact(ctx, p["party"], ContactKind.CUSTOMER)
            ref = p.get("reference")
            if ref and await _reference_seen(ctx, ref):
                return Applied(Reply(f"Ce paiement ({ref}) était déjà noté."))
            await ledger.record_entry(
                ctx.session, shop_id=sid, kind=EntryKind.PAYMENT_RECEIVED, amount=p["amount"], contact_id=contact.id,
                source=p.get("source") or EntrySource.TEXT, payment_reference=ref, created_by=uid,
            )  # fmt: skip
            left = await ledger.contact_balance(ctx.session, shop_id=sid, contact_id=contact.id)
            tail = f"Il reste {money(left)} FCFA à payer." if left > 0 else "Sa dette est soldée. ✅"
            return Applied(Reply(f"C'est noté. {contact.name} a payé {money(p['amount'])} FCFA. {tail}"))
        if kind == "supplier_debt":
            contact = await _party_contact(ctx, p["party"], ContactKind.SUPPLIER)
            due = date.fromisoformat(p["due_date"]) if p.get("due_date") else None
            await ledger.record_entry(
                ctx.session, shop_id=sid, kind=EntryKind.SUPPLIER_PURCHASE, amount=p["amount"], paid=p["paid"],
                contact_id=contact.id, due_date=due, note=p.get("items"), created_by=uid,
            )  # fmt: skip
            owed = await ledger.contact_balance(ctx.session, shop_id=sid, contact_id=contact.id)
            tail = f" Je vous le rappelle avant le {due:%d/%m}." if due and owed > 0 else ""
            return Applied(Reply(f"C'est noté. Vous devez {money(owed)} FCFA à {contact.name}.{tail}"))
        if kind == "supplier_payment":
            contact = await _party_contact(ctx, p["party"], ContactKind.SUPPLIER)
            await ledger.record_entry(
                ctx.session, shop_id=sid, kind=EntryKind.SUPPLIER_PAYMENT, amount=p["amount"],
                contact_id=contact.id, created_by=uid,
            )  # fmt: skip
            owed = await ledger.contact_balance(ctx.session, shop_id=sid, contact_id=contact.id)
            tail = f"Il vous reste {money(owed)} FCFA à lui payer." if owed > 0 else "Vous ne lui devez plus rien."
            return Applied(Reply(f"C'est noté. {tail}"))
        if kind == "expense":
            await ledger.record_entry(
                ctx.session,
                shop_id=sid,
                kind=EntryKind.EXPENSE,
                amount=p["amount"],
                note=p["label"],
                created_by=uid,
            )
            return Applied(Reply(f"C'est noté : {p['label']}, {money(p['amount'])} FCFA."))
        if kind == "stock":
            return await _apply_stock(ctx, p)
        if kind == "correction":
            await _reverse(ctx, p["entry_id"])
            return Applied(Reply("C'est annulé. Rien n'a été effacé : l'opération reste visible dans l'historique."))
        if kind == "import":
            return await _apply_import(ctx, p)
        if kind == "seller":
            ctx.session.add(AppUser(shop_id=sid, whatsapp_id=p["phone"], name=p.get("name"), role="seller"))
            who = p.get("name") or "Cette personne"
            return Applied(
                Reply(f"C'est fait. Demandez à {who} d'écrire « Bonjour » à ce numéro WhatsApp pour commencer.")
            )
    except LedgerError as exc:
        log.warning("pending %s refused by the ledger: %s", pending.id, exc)
        return Applied(Reply(f"Je ne peux pas noter cela : {exc}."))
    return Applied(Reply("Je ne sais plus quoi noter. Pouvez-vous redire ?"))


async def _apply_sale(ctx: Ctx, p: dict) -> Applied:
    contact = await _party_contact(ctx, p["party"], ContactKind.CUSTOMER) if p["party"]["name"] else None
    lines = [Line(ln["product"], ln["quantity"], ln.get("unit"), ln["unit_price"]) for ln in p["lines"]]
    entry = await ledger.record_entry(
        ctx.session, shop_id=ctx.shop.id, kind=EntryKind.SALE, lines=lines, paid=p["paid"],
        contact_id=contact.id if contact else None, source=ctx.source, media_id=ctx.media_id, created_by=ctx.user.id,
    )  # fmt: skip
    warnings = []
    for ln in lines:
        await queries.learn_price(ctx.session, ctx.shop.id, ln.product, ln.unit, ln.unit_price)
        product = await queries.lower_stock_if_tracked(ctx.session, ctx.shop.id, ln.product, ln.quantity)
        if product is not None and (product.stock or 0) <= LOW_STOCK:
            warnings.append(
                f"⚠️ Il ne reste que {product.stock} {product.name}."
                if product.stock > 0
                else f"⚠️ Plus de {product.name} en stock."
            )
    owed = entry.debt_delta
    text = "C'est noté." + (f" {contact.name} vous doit {money(owed)} FCFA." if contact and owed else "")
    if warnings:
        text += "\n" + "\n".join(warnings)
    return Applied(Reply(text), sale_entry_id=entry.id)


async def _apply_stock(ctx: Ctx, p: dict) -> Applied:
    product = await queries.upsert_product(ctx.session, ctx.shop.id, p["product"], p.get("unit"))
    new = {
        "add": (product.stock or 0) + p["quantity"],
        "remove": (product.stock or 0) - p["quantity"],
        "set": p["quantity"],
    }[p["mode"]]
    product.stock = new
    ctx.session.add(product)
    text = f"C'est noté. Stock de {product.name} : *{new}*."
    if new <= LOW_STOCK:
        text += " ⚠️ C'est bas."
    return Applied(Reply(text))


async def _reverse(ctx: Ctx, entry_id: int) -> None:
    from app.db.models import Entry

    entry = await ctx.session.get(Entry, entry_id)
    await ledger.reverse_entry(ctx.session, shop_id=ctx.shop.id, entry_id=entry_id, created_by=ctx.user.id)
    if entry and entry.kind == EntryKind.SALE:  # the goods go back on the shelf
        for ln in entry.lines:
            product = await queries.get_product(ctx.session, ctx.shop.id, ln["product"])
            if product is not None and product.stock is not None:
                product.stock += ln["quantity"]
                ctx.session.add(product)


async def _apply_import(ctx: Ctx, p: dict) -> Applied:
    created = 0
    for ln in p["lines"]:
        matches = await queries.find_contacts(ctx.session, ctx.shop.id, ln["customer"], ContactKind.CUSTOMER)
        contact = (
            matches[0] if len(matches) == 1 else await queries.create_contact(ctx.session, ctx.shop.id, ln["customer"])
        )
        note = " · ".join(x for x in ("cahier", ln.get("description"), ln.get("date")) if x)
        await ledger.record_entry(
            ctx.session, shop_id=ctx.shop.id, kind=EntryKind.SALE, amount=ln["amount_owed"], paid=0,
            contact_id=contact.id, source=EntrySource.NOTEBOOK_PHOTO, media_id=p.get("media_id"),
            note=note, created_by=ctx.user.id,
        )  # fmt: skip
        created += 1
    total = sum(ln["amount_owed"] for ln in p["lines"])
    return Applied(
        Reply(
            f"C'est noté : {created} dette(s) reprises du cahier, {money(total)} FCFA au total. "
            "Écrivez « qui me doit ? » pour les voir."
        )
    )


# --- picking among ambiguous contacts ---


async def pick_party(ctx: Ctx, pending: PendingAction, choice: str) -> Reply:
    payload = dict(pending.payload)
    party = dict(payload["party"])
    if choice == "new":
        party.update(id=None, new=True, candidates=[])
    else:
        contact = await ctx.session.get(Contact, int(choice))
        if contact is None or contact.shop_id != ctx.shop.id:
            return Reply("Je ne retrouve plus ce contact. Pouvez-vous redire ?")
        party.update(id=contact.id, name=contact.name, new=False, candidates=[])
        if pending.kind == "payment":
            payload["balance_before"] = await ledger.contact_balance(
                ctx.session, shop_id=ctx.shop.id, contact_id=contact.id
            )
    payload["party"] = party
    pending.payload = payload
    ctx.session.add(pending)
    return Reply(describe(pending), buttons=confirm_buttons(pending.id), kind="proposal")


async def mark_corrected(ctx: Ctx, pending: PendingAction) -> None:
    pending.payload = {**pending.payload, "corrected": True}
    pending.status = PendingStatus.CANCELLED
    ctx.session.add(pending)
