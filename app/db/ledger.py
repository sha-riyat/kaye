"""Ledger writes and balance queries. Every query is scoped by shop_id.

Only this module creates entries, and only from validated values: the model never writes here
directly. Totals are recomputed from the lines (quantity x unit price) by the code.
"""

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models import Contact, ContactKind, Entry, EntryKind, EntrySource


class LedgerError(Exception):
    pass


@dataclass(frozen=True)
class Line:
    product: str
    quantity: int
    unit: str | None
    unit_price: int

    @property
    def total(self) -> int:
        return self.quantity * self.unit_price

    def as_json(self) -> dict:
        return {
            "product": self.product,
            "quantity": self.quantity,
            "unit": self.unit,
            "unit_price": self.unit_price,
            "total": self.total,
        }


def debt_delta(kind: EntryKind, amount: int, paid: int = 0) -> int:
    """How much this operation changes what the contact owes us (or we owe a supplier)."""
    if amount < 0 or paid < 0:
        raise LedgerError("amounts must be positive")
    if kind in (EntryKind.SALE, EntryKind.SUPPLIER_PURCHASE):
        if paid > amount:
            raise LedgerError(f"paid {paid} exceeds total {amount}")
        return amount - paid
    return -amount


async def record_entry(
    session: AsyncSession,
    *,
    shop_id: int,
    kind: EntryKind,
    amount: int | None = None,
    paid: int = 0,
    lines: list[Line] | None = None,
    contact_id: int | None = None,
    source: EntrySource = EntrySource.TEXT,
    media_id: int | None = None,
    payment_reference: str | None = None,
    due_date: date | None = None,
    note: str | None = None,
    created_by: int | None = None,
) -> Entry:
    lines = lines or []
    if lines:
        computed = sum(line.total for line in lines)
        if amount is not None and amount != computed:
            raise LedgerError(f"amount {amount} does not match lines total {computed}")
        amount = computed
    if amount is None:
        raise LedgerError("amount or lines required")
    delta = debt_delta(kind, amount, paid)
    if delta != 0 and contact_id is None:
        raise LedgerError("an operation that leaves a debt needs a contact")
    if contact_id is not None:
        await _contact_in_shop(session, shop_id, contact_id)

    entry = Entry(
        shop_id=shop_id,
        kind=kind,
        contact_id=contact_id,
        amount=amount,
        debt_delta=delta,
        lines=[line.as_json() for line in lines],
        source=source,
        media_id=media_id,
        payment_reference=payment_reference,
        due_date=due_date,
        note=note,
        created_by=created_by,
    )
    session.add(entry)
    await session.flush()
    return entry


async def reverse_entry(
    session: AsyncSession, *, shop_id: int, entry_id: int, created_by: int | None = None
) -> Entry:
    """Cancel an entry by inserting its negation. The original is kept for the audit trail."""
    original = await session.get(Entry, entry_id)
    if original is None or original.shop_id != shop_id:
        raise LedgerError("entry not found")
    if original.reverses_entry_id is not None:
        raise LedgerError("cannot reverse a reversal")
    already = await session.exec(select(Entry.id).where(Entry.reverses_entry_id == entry_id))
    if already.first() is not None:
        raise LedgerError("entry already reversed")

    reversal = Entry(
        shop_id=shop_id,
        kind=original.kind,
        contact_id=original.contact_id,
        amount=-original.amount,
        debt_delta=-original.debt_delta,
        lines=original.lines,
        source=original.source,
        note=f"correction of #{original.id}",
        reverses_entry_id=original.id,
        created_by=created_by,
    )
    session.add(reversal)
    await session.flush()
    return reversal


async def last_active_entry(
    session: AsyncSession, *, shop_id: int, created_by: int | None = None
) -> Entry | None:
    """Most recent entry that is neither a reversal nor reversed."""
    reversed_ids = select(Entry.reverses_entry_id).where(
        Entry.shop_id == shop_id, col(Entry.reverses_entry_id).is_not(None)
    )
    query = select(Entry).where(
        Entry.shop_id == shop_id,
        col(Entry.reverses_entry_id).is_(None),
        col(Entry.id).not_in(reversed_ids),
    )
    if created_by is not None:
        query = query.where(Entry.created_by == created_by)
    result = await session.exec(query.order_by(col(Entry.created_at).desc(), col(Entry.id).desc()).limit(1))
    return result.first()


async def contact_balance(session: AsyncSession, *, shop_id: int, contact_id: int) -> int:
    result = await session.exec(
        select(func.coalesce(func.sum(Entry.debt_delta), 0)).where(
            Entry.shop_id == shop_id, Entry.contact_id == contact_id
        )
    )
    return int(result.one())


@dataclass(frozen=True)
class Debtor:
    contact: Contact
    balance: int
    oldest_credit_at: datetime | None


async def debtors(
    session: AsyncSession, *, shop_id: int, kind: ContactKind = ContactKind.CUSTOMER
) -> list[Debtor]:
    """Contacts with a positive balance, largest first."""
    balance = func.sum(Entry.debt_delta).label("balance")
    oldest = func.min(Entry.created_at).filter(Entry.debt_delta > 0).label("oldest")
    query = (
        select(Contact, balance, oldest)
        .join(Entry, col(Entry.contact_id) == Contact.id)
        .where(Contact.shop_id == shop_id, Entry.shop_id == shop_id, Contact.kind == kind)
        .group_by(col(Contact.id))
        .having(balance > 0)
        .order_by(balance.desc(), oldest.asc())
    )
    rows = await session.exec(query)
    return [Debtor(contact=c, balance=int(b), oldest_credit_at=o) for c, b, o in rows.all()]


async def _contact_in_shop(session: AsyncSession, shop_id: int, contact_id: int) -> None:
    contact = await session.get(Contact, contact_id)
    if contact is None or contact.shop_id != shop_id:
        raise LedgerError("contact not found")
