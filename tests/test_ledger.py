"""Ledger tests against a real Postgres (set TEST_DATABASE_URL, e.g. a local Docker container)."""

import os

import pytest
from sqlalchemy import text
from sqlmodel import SQLModel

from app.db.engine import Database
from app.db.ledger import (
    LedgerError,
    Line,
    contact_balance,
    debt_delta,
    debtors,
    last_active_entry,
    record_entry,
    reverse_entry,
)
from app.db.models import AppUser, Contact, ContactKind, EntryKind, Shop
from app.dedup import PostgresDeduplicator

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")


# --- pure logic, no database ---


@pytest.mark.parametrize(
    ("kind", "amount", "paid", "expected"),
    [
        (EntryKind.SALE, 15_000, 10_000, 5_000),
        (EntryKind.SALE, 15_000, 15_000, 0),
        (EntryKind.PAYMENT_RECEIVED, 5_000, 0, -5_000),
        (EntryKind.SUPPLIER_PURCHASE, 50_000, 0, 50_000),
        (EntryKind.SUPPLIER_PAYMENT, 20_000, 0, -20_000),
    ],
)
def test_debt_delta(kind, amount, paid, expected):
    assert debt_delta(kind, amount, paid) == expected


def test_overpaid_sale_is_rejected():
    with pytest.raises(LedgerError):
        debt_delta(EntryKind.SALE, 1_000, 2_000)


# --- database ---


@pytest.fixture
async def db():
    database = Database(TEST_DATABASE_URL)
    async with database.engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
    yield database
    await database.dispose()


@pytest.fixture
async def shop(db):
    async with db.session() as s:
        shop = Shop(name="Boutique Test")
        s.add(shop)
        await s.flush()
        owner = AppUser(shop_id=shop.id, whatsapp_id="22890000001", name="Patron")
        ama = Contact(shop_id=shop.id, name="Ama", aliases=["maman Ama"])
        kofi = Contact(shop_id=shop.id, name="Kofi")
        koffi = Contact(shop_id=shop.id, name="Grossiste Koffi", kind=ContactKind.SUPPLIER)
        s.add_all([owner, ama, kofi, koffi])
        await s.flush()
        return {"shop": shop.id, "owner": owner.id, "ama": ama.id, "kofi": kofi.id, "koffi": koffi.id}


@needs_db
async def test_credit_sale_then_payment(db, shop):
    async with db.session() as s:
        sale = await record_entry(
            s,
            shop_id=shop["shop"],
            kind=EntryKind.SALE,
            lines=[Line("riz", 3, "sac", 5_000)],
            paid=10_000,
            contact_id=shop["ama"],
            created_by=shop["owner"],
        )
        assert sale.amount == 15_000
        assert sale.debt_delta == 5_000
        assert sale.lines[0]["total"] == 15_000
        assert await contact_balance(s, shop_id=shop["shop"], contact_id=shop["ama"]) == 5_000

        await record_entry(
            s,
            shop_id=shop["shop"],
            kind=EntryKind.PAYMENT_RECEIVED,
            amount=5_000,
            contact_id=shop["ama"],
            payment_reference="TMONEY-123",
        )
        assert await contact_balance(s, shop_id=shop["shop"], contact_id=shop["ama"]) == 0


@needs_db
async def test_amount_mismatch_with_lines_is_rejected(db, shop):
    async with db.session() as s:
        with pytest.raises(LedgerError, match="does not match"):
            await record_entry(
                s,
                shop_id=shop["shop"],
                kind=EntryKind.SALE,
                amount=14_000,
                lines=[Line("riz", 3, "sac", 5_000)],
                contact_id=shop["ama"],
            )


@needs_db
async def test_debt_without_contact_is_rejected(db, shop):
    async with db.session() as s:
        with pytest.raises(LedgerError, match="needs a contact"):
            await record_entry(s, shop_id=shop["shop"], kind=EntryKind.SALE, amount=1_000)


@needs_db
async def test_cash_sale_without_contact_is_fine(db, shop):
    async with db.session() as s:
        entry = await record_entry(s, shop_id=shop["shop"], kind=EntryKind.SALE, amount=1_000, paid=1_000)
        assert entry.debt_delta == 0


@needs_db
async def test_contact_from_another_shop_is_rejected(db, shop):
    async with db.session() as s:
        other = Shop(name="Autre boutique")
        s.add(other)
        await s.flush()
        with pytest.raises(LedgerError, match="contact not found"):
            await record_entry(s, shop_id=other.id, kind=EntryKind.SALE, amount=1_000, contact_id=shop["ama"])


@needs_db
async def test_same_mobile_money_reference_cannot_be_counted_twice(db, shop):
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        async with db.session() as s:
            for _ in range(2):
                await record_entry(
                    s,
                    shop_id=shop["shop"],
                    kind=EntryKind.PAYMENT_RECEIVED,
                    amount=2_000,
                    contact_id=shop["ama"],
                    payment_reference="FLOOZ-999",
                )


@needs_db
async def test_reversal_cancels_entry_and_keeps_history(db, shop):
    async with db.session() as s:
        sale = await record_entry(s, shop_id=shop["shop"], kind=EntryKind.SALE, amount=8_000, contact_id=shop["ama"])
        reversal = await reverse_entry(s, shop_id=shop["shop"], entry_id=sale.id)

        assert reversal.amount == -8_000
        assert reversal.reverses_entry_id == sale.id
        assert await contact_balance(s, shop_id=shop["shop"], contact_id=shop["ama"]) == 0
        assert await last_active_entry(s, shop_id=shop["shop"]) is None

        with pytest.raises(LedgerError, match="already reversed"):
            await reverse_entry(s, shop_id=shop["shop"], entry_id=sale.id)
        with pytest.raises(LedgerError, match="reversal"):
            await reverse_entry(s, shop_id=shop["shop"], entry_id=reversal.id)
        count = await s.exec(text("select count(*) from entry"))
        assert count.one()[0] == 2


@needs_db
async def test_last_active_entry_skips_reversed_ones(db, shop):
    async with db.session() as s:
        first = await record_entry(s, shop_id=shop["shop"], kind=EntryKind.SALE, amount=1_000, paid=1_000)
        second = await record_entry(s, shop_id=shop["shop"], kind=EntryKind.SALE, amount=2_000, paid=2_000)
        assert (await last_active_entry(s, shop_id=shop["shop"])).id == second.id

        await reverse_entry(s, shop_id=shop["shop"], entry_id=second.id)
        assert (await last_active_entry(s, shop_id=shop["shop"])).id == first.id


@needs_db
async def test_debtors_sorted_by_balance_and_split_by_kind(db, shop):
    async with db.session() as s:
        sid = shop["shop"]
        await record_entry(s, shop_id=sid, kind=EntryKind.SALE, amount=3_000, contact_id=shop["ama"])
        await record_entry(s, shop_id=sid, kind=EntryKind.SALE, amount=9_000, contact_id=shop["kofi"])
        await record_entry(s, shop_id=sid, kind=EntryKind.PAYMENT_RECEIVED, amount=1_000, contact_id=shop["kofi"])
        await record_entry(s, shop_id=sid, kind=EntryKind.SUPPLIER_PURCHASE, amount=50_000, contact_id=shop["koffi"])

        customers = await debtors(s, shop_id=sid)
        assert [(d.contact.name, d.balance) for d in customers] == [("Kofi", 8_000), ("Ama", 3_000)]
        assert all(d.oldest_credit_at is not None for d in customers)

        suppliers = await debtors(s, shop_id=sid, kind=ContactKind.SUPPLIER)
        assert [(d.contact.name, d.balance) for d in suppliers] == [("Grossiste Koffi", 50_000)]


@needs_db
async def test_postgres_dedup(db):
    dedup = PostgresDeduplicator(db)
    assert await dedup.claim("wamid.A") is True
    assert await dedup.claim("wamid.A") is False
    assert await dedup.claim("wamid.B") is True
