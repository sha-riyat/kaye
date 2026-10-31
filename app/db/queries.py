"""Everything the agent reads or writes around the ledger: shops, contacts, prices, stock, pending
actions, receipts, model costs. Every query is scoped by shop_id."""

import unicodedata
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models import (
    AppUser,
    Contact,
    ContactKind,
    MessageLog,
    ModelCall,
    PendingAction,
    PendingStatus,
    Product,
    Receipt,
    Shop,
    UnitPrice,
)

PENDING_TTL = timedelta(minutes=30)


def norm(text: str) -> str:
    """Lowercase, no accents, single spaces: 'Maman Ámá' -> 'maman ama'."""
    stripped = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return " ".join(stripped.lower().split())


def utcnow() -> datetime:
    return datetime.now(UTC)


def day_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    """Calendar day in Africa/Lome, which is UTC all year."""
    now = now or utcnow()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


# --- shops and users ---


async def user_by_whatsapp(session: AsyncSession, wa_id: str) -> AppUser | None:
    return (await session.exec(select(AppUser).where(AppUser.whatsapp_id == wa_id))).first()


async def create_shop_with_owner(session: AsyncSession, wa_id: str, name: str | None) -> tuple[Shop, AppUser]:
    shop = Shop(name="")  # empty until the merchant tells us
    session.add(shop)
    await session.flush()
    user = AppUser(shop_id=shop.id, whatsapp_id=wa_id, name=name, role="owner")
    session.add(user)
    await session.flush()
    return shop, user


async def all_shops(session: AsyncSession) -> list[Shop]:
    return list((await session.exec(select(Shop).where(Shop.name != ""))).all())


async def owner_of(session: AsyncSession, shop_id: int) -> AppUser | None:
    return (await session.exec(select(AppUser).where(AppUser.shop_id == shop_id, AppUser.role == "owner"))).first()


# --- contacts ---


async def match_contacts(
    session: AsyncSession, shop_id: int, name: str, kind: ContactKind | None = None
) -> tuple[list[Contact], bool]:
    """Contacts matching a spoken name, and whether the match is confident.

    Confident: the exact name or alias, or a shortening of it ("Ama" for "Ama Koudjo").
    Not confident: only a word in common ("Ama Mensah" vs "Ama Koudjo"): never merged silently.
    """
    query = select(Contact).where(Contact.shop_id == shop_id)
    if kind:
        query = query.where(Contact.kind == kind)
    contacts = (await session.exec(query)).all()
    wanted = norm(name)
    if not wanted:
        return [], False

    def names(c: Contact) -> list[str]:
        return [norm(c.name), *(norm(a) for a in c.aliases)]

    exact = [c for c in contacts if wanted in names(c)]
    if exact:
        return exact, True
    words = set(wanted.split())
    shortened = [c for c in contacts if any(words <= set(n.split()) for n in names(c))]
    if shortened:
        return shortened, True
    return [c for c in contacts if any(words & set(n.split()) for n in names(c))], False


async def find_contacts(
    session: AsyncSession, shop_id: int, name: str, kind: ContactKind | None = None
) -> list[Contact]:
    return (await match_contacts(session, shop_id, name, kind))[0]


async def create_contact(
    session: AsyncSession,
    shop_id: int,
    name: str,
    kind: ContactKind = ContactKind.CUSTOMER,
    phone: str | None = None,
) -> Contact:
    contact = Contact(shop_id=shop_id, name=name.strip(), kind=kind, phone=phone, aliases=[])
    session.add(contact)
    await session.flush()
    return contact


async def remember_alias(session: AsyncSession, contact: Contact, spoken: str) -> None:
    """'Ama du marché' said once for 'Ama Koudjo' is recognised next time."""
    spoken = spoken.strip()
    if set(norm(spoken).split()) <= set(norm(contact.name).split()):
        return  # just a shortening of the name
    if spoken and norm(spoken) not in {norm(contact.name), *(norm(a) for a in contact.aliases)}:
        contact.aliases = [*contact.aliases, spoken]
        session.add(contact)


async def contact_by_phone(session: AsyncSession, shop_id: int, phone: str) -> Contact | None:
    digits = "".join(ch for ch in phone if ch.isdigit())[-8:]
    if len(digits) < 8:
        return None
    contacts = (await session.exec(select(Contact).where(Contact.shop_id == shop_id, Contact.phone.is_not(None)))).all()  # type: ignore[union-attr]
    for c in contacts:
        if "".join(ch for ch in (c.phone or "") if ch.isdigit())[-8:] == digits:
            return c
    return None


# --- products, prices, stock ---


def _product_key(name: str) -> str:
    """'Sacs de riz' and 'sac de riz' are the same product; 'riz' and 'riz parfumé' are not."""
    return " ".join(w[:-1] if len(w) > 3 and w.endswith("s") else w for w in norm(name).split())


async def get_product(session: AsyncSession, shop_id: int, name: str) -> Product | None:
    wanted = _product_key(name)
    products = (await session.exec(select(Product).where(Product.shop_id == shop_id))).all()
    return next((p for p in products if _product_key(p.name) == wanted), None)


async def usual_price(session: AsyncSession, shop_id: int, product: str, unit: str | None) -> int | None:
    p = await get_product(session, shop_id, product)
    if p is None:
        return None
    query = select(UnitPrice).where(UnitPrice.shop_id == shop_id, UnitPrice.product_id == p.id)
    prices = (await session.exec(query)).all()
    wanted = norm(unit) if unit else norm(p.default_unit or "")
    for price in prices:
        if norm(price.unit) == wanted:
            return price.price
    return prices[0].price if len(prices) == 1 and not unit else None


async def learn_price(session: AsyncSession, shop_id: int, product: str, unit: str | None, price: int) -> None:
    p = await upsert_product(session, shop_id, product, unit)
    unit_name = unit or p.default_unit or "unité"
    existing = (
        await session.exec(select(UnitPrice).where(UnitPrice.product_id == p.id, UnitPrice.unit == unit_name))
    ).first()
    if existing:
        existing.price = price
        existing.updated_at = utcnow()
        session.add(existing)
    else:
        session.add(UnitPrice(shop_id=shop_id, product_id=p.id, unit=unit_name, price=price))


async def upsert_product(session: AsyncSession, shop_id: int, name: str, unit: str | None = None) -> Product:
    p = await get_product(session, shop_id, name)
    if p is None:
        p = Product(shop_id=shop_id, name=name.strip().lower(), default_unit=unit)
        session.add(p)
        await session.flush()
    elif unit and not p.default_unit:
        p.default_unit = unit
        session.add(p)
    return p


async def adjust_stock(session: AsyncSession, shop_id: int, name: str, delta: int, unit: str | None = None) -> Product:
    """Add or remove units. A sale only lowers stock of products whose stock is already tracked."""
    p = await upsert_product(session, shop_id, name, unit)
    p.stock = (p.stock or 0) + delta
    session.add(p)
    return p


async def lower_stock_if_tracked(session: AsyncSession, shop_id: int, name: str, quantity: int) -> Product | None:
    p = await get_product(session, shop_id, name)
    if p is None or p.stock is None:
        return None
    p.stock -= quantity
    session.add(p)
    return p


async def tracked_products(session: AsyncSession, shop_id: int) -> list[Product]:
    query = select(Product).where(Product.shop_id == shop_id, col(Product.stock).is_not(None)).order_by(Product.name)
    return list((await session.exec(query)).all())


# --- pending actions ---


async def create_pending(
    session: AsyncSession, *, shop_id: int, user_id: int, kind: str, payload: dict, wamid: str | None
) -> PendingAction:
    pending = PendingAction(
        shop_id=shop_id,
        user_id=user_id,
        kind=kind,
        payload=payload,
        source_wamid=wamid,
        expires_at=utcnow() + PENDING_TTL,
    )
    session.add(pending)
    await session.flush()
    return pending


async def recent_same_proposal(session: AsyncSession, user_id: int, kind: str, payload: dict) -> bool:
    """True if the same operation was proposed (and not cancelled) in the last 15 minutes."""
    since = utcnow() - timedelta(minutes=15)
    query = select(PendingAction).where(
        PendingAction.user_id == user_id,
        PendingAction.kind == kind,
        PendingAction.created_at >= since,
        col(PendingAction.status).in_([PendingStatus.PENDING, PendingStatus.CONFIRMED]),
    )
    rows = (await session.exec(query)).all()
    return any(_same(r.payload, payload) for r in rows)


def _same(a: dict, b: dict) -> bool:
    """Same operation, ignoring bookkeeping fields that differ between two proposals of it."""
    skip = {"candidates", "balance_before", "warning", "corrected", "before", "after"}

    def clean(d):
        if isinstance(d, dict):
            return {k: clean(v) for k, v in d.items() if k not in skip}
        if isinstance(d, list):
            return [clean(v) for v in d]
        return d

    return clean(a) == clean(b)


async def get_pending(session: AsyncSession, shop_id: int, pending_id: int) -> PendingAction | None:
    """Fetched with a row lock: two quick taps on "Oui" must not write twice."""
    pending = await session.get(PendingAction, pending_id, with_for_update=True)
    return pending if pending and pending.shop_id == shop_id else None


async def settle_pending(session: AsyncSession, pending: PendingAction, status: PendingStatus) -> None:
    pending.status = status
    session.add(pending)


async def open_questions(session: AsyncSession, user_id: int) -> list[PendingAction]:
    """Questions we asked the merchant that are still waiting for an answer, oldest first."""
    query = (
        select(PendingAction)
        .where(
            PendingAction.user_id == user_id,
            PendingAction.kind == "clarify",
            PendingAction.status == PendingStatus.PENDING,
            PendingAction.expires_at > utcnow(),
        )
        .order_by(col(PendingAction.id))
    )
    return list((await session.exec(query)).all())


async def last_corrected(session: AsyncSession, user_id: int) -> PendingAction | None:
    """The proposal the merchant just asked to fix, if any (within 10 minutes)."""
    since = utcnow() - timedelta(minutes=10)
    query = (
        select(PendingAction)
        .where(
            PendingAction.user_id == user_id,
            PendingAction.status == PendingStatus.CANCELLED,
            PendingAction.created_at >= since,
        )
        .order_by(col(PendingAction.id).desc())
        .limit(5)
    )
    rows = (await session.exec(query)).all()
    return next((r for r in rows if r.payload.get("corrected")), None)


# --- receipts ---


async def next_receipt_number(session: AsyncSession, shop_id: int) -> int:
    current = (await session.exec(select(func.max(Receipt.number)).where(Receipt.shop_id == shop_id))).one()
    return (current or 0) + 1


# --- model cost accounting ---


async def log_model_call(
    session: AsyncSession,
    *,
    shop_id: int | None,
    model: str,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
    audio_ms: int = 0,
) -> None:
    session.add(
        ModelCall(
            shop_id=shop_id,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            audio_ms=audio_ms,
            cost_usd=Decimal(str(round(cost_usd, 6))),
        )
    )


async def calls_today(session: AsyncSession, shop_id: int) -> int:
    start, end = day_bounds()
    query = (
        select(func.count())
        .select_from(ModelCall)
        .where(ModelCall.shop_id == shop_id, ModelCall.created_at >= start, ModelCall.created_at < end)
    )
    return int((await session.exec(query)).one())


async def spent_today(session: AsyncSession) -> float:
    start, end = day_bounds()
    query = select(func.coalesce(func.sum(ModelCall.cost_usd), 0)).where(
        ModelCall.created_at >= start, ModelCall.created_at < end
    )
    return float((await session.exec(query)).one())


# --- conversation memory ---

MEMORY_TURNS = 8
MEMORY_WINDOW = timedelta(hours=6)


async def remember(session: AsyncSession, shop_id: int, user_id: int, role: str, text: str) -> None:
    if text:
        session.add(MessageLog(shop_id=shop_id, user_id=user_id, role=role, text=text[:600]))


async def recent_turns(session: AsyncSession, user_id: int) -> list[MessageLog]:
    """The last few messages of this conversation (not older than a few hours), oldest first."""
    query = (
        select(MessageLog)
        .where(MessageLog.user_id == user_id, MessageLog.created_at >= utcnow() - MEMORY_WINDOW)
        .order_by(col(MessageLog.id).desc())
        .limit(MEMORY_TURNS)
    )
    return list(reversed((await session.exec(query)).all()))


# --- erasure ---

ERASE_ORDER = [
    "receipt", "entry", "pending_action", "message_log", "unit_price", "product", "contact", "media", "model_call",
]  # fmt: skip


async def erase_shop_data(session: AsyncSession, shop_id: int) -> None:
    """Delete everything a shop recorded, its users and the shop itself: the next message from the
    owner is a first contact again."""
    from sqlalchemy import text

    await session.exec(
        text("DELETE FROM entry WHERE shop_id = :s AND reverses_entry_id IS NOT NULL").bindparams(s=shop_id)
    )
    for table in ERASE_ORDER:
        await session.exec(text(f"DELETE FROM {table} WHERE shop_id = :s").bindparams(s=shop_id))
    await session.exec(text("DELETE FROM app_user WHERE shop_id = :s").bindparams(s=shop_id))
    await session.exec(text("DELETE FROM shop WHERE id = :s").bindparams(s=shop_id))
