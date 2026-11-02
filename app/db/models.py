"""Database tables.

Balances are never stored: they are summed from `entry.debt_delta`, so every figure traces back to
the message that created it. Nothing is deleted: a correction inserts a reversing entry.
Amounts are integer FCFA (XOF).
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def _created_at() -> Any:
    return Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )


def _json(default_factory=dict) -> Any:
    return Field(default_factory=default_factory, sa_column=Column(JSONB, nullable=False))


def _money(nullable: bool = False) -> Any:
    return Field(default=None if nullable else 0, sa_column=Column(BigInteger, nullable=nullable))


def _fk(target: str, nullable: bool = False, **kwargs) -> Any:
    return Field(
        default=None,
        sa_column=Column(BigInteger, ForeignKey(target), nullable=nullable, index=True, **kwargs),
    )


class Role(StrEnum):
    OWNER = "owner"
    SELLER = "seller"


class ContactKind(StrEnum):
    CUSTOMER = "customer"
    SUPPLIER = "supplier"


class EntryKind(StrEnum):
    SALE = "sale"
    PAYMENT_RECEIVED = "payment_received"
    SUPPLIER_PURCHASE = "supplier_purchase"
    SUPPLIER_PAYMENT = "supplier_payment"
    EXPENSE = "expense"  # rent, transport, bags...: money out, nothing owed


class EntrySource(StrEnum):
    TEXT = "text"
    VOICE = "voice"
    NOTEBOOK_PHOTO = "notebook_photo"
    MOBILE_MONEY = "mobile_money"


class PendingStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class Shop(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True, sa_type=BigInteger)
    name: str
    logo_key: str | None = None  # R2 object key
    currency: str = "XOF"
    timezone: str = "Africa/Lome"
    summary_hour: int = 20  # local hour of the evening summary
    language: str | None = Field(default=None, sa_type=String(2))  # fr, en (judges); None = not chosen yet
    created_at: datetime | None = _created_at()


class AppUser(SQLModel, table=True):
    """A WhatsApp number allowed to act on a shop. `user` is reserved in Postgres."""

    __tablename__ = "app_user"

    id: int | None = Field(default=None, primary_key=True, sa_type=BigInteger)
    shop_id: int = _fk("shop.id")
    whatsapp_id: str = Field(sa_type=String(32), unique=True)
    name: str | None = None
    role: str = Field(default=Role.OWNER, sa_type=String(16))
    created_at: datetime | None = _created_at()


class Contact(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True, sa_type=BigInteger)
    shop_id: int = _fk("shop.id")
    name: str
    phone: str | None = Field(default=None, sa_type=String(32))
    kind: str = Field(default=ContactKind.CUSTOMER, sa_type=String(16))
    aliases: list[str] = _json(list)  # "Ama", "maman Ama", "Ama du marché"
    created_at: datetime | None = _created_at()


class Product(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("shop_id", "name"),)

    id: int | None = Field(default=None, primary_key=True, sa_type=BigInteger)
    shop_id: int = _fk("shop.id")
    name: str
    default_unit: str | None = None
    stock: int | None = None  # None = not tracked yet; set by the first stock entry
    created_at: datetime | None = _created_at()


class UnitPrice(SQLModel, table=True):
    """Usual price learned per product and local unit (tas, bol, sac, tine...)."""

    __tablename__ = "unit_price"
    __table_args__ = (UniqueConstraint("product_id", "unit"),)

    id: int | None = Field(default=None, primary_key=True, sa_type=BigInteger)
    shop_id: int = _fk("shop.id")
    product_id: int = _fk("product.id")
    unit: str
    price: int = _money()
    updated_at: datetime | None = _created_at()


class Media(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True, sa_type=BigInteger)
    shop_id: int = _fk("shop.id")
    kind: str = Field(sa_type=String(16))  # audio, image, receipt, logo
    storage_key: str
    mime_type: str | None = None
    wa_media_id: str | None = None
    created_at: datetime | None = _created_at()


class Entry(SQLModel, table=True):
    """One ledger line ("transaction" in the plan; renamed because it is a SQL keyword).

    `debt_delta` > 0 means the contact owes more (customer) or we owe the contact more (supplier).
    A correction is a new entry with negated amounts and `reverses_entry_id` set.
    """

    __table_args__ = (
        UniqueConstraint("shop_id", "payment_reference"),
        Index("ix_entry_shop_created", "shop_id", "created_at"),
    )

    id: int | None = Field(default=None, primary_key=True, sa_type=BigInteger)
    shop_id: int = _fk("shop.id")
    kind: str = Field(sa_type=String(24))
    contact_id: int | None = _fk("contact.id", nullable=True)
    amount: int = _money()  # value of the operation: sale total, payment amount...
    debt_delta: int = _money()
    lines: list[dict] = _json(list)  # [{"product", "quantity", "unit", "unit_price", "total"}]
    source: str = Field(default=EntrySource.TEXT, sa_type=String(24))
    media_id: int | None = _fk("media.id", nullable=True)
    payment_reference: str | None = None  # mobile money transaction id, prevents double counting
    due_date: date | None = None  # supplier debts
    note: str | None = None
    reverses_entry_id: int | None = _fk("entry.id", nullable=True, unique=True)
    created_by: int | None = _fk("app_user.id", nullable=True)
    created_at: datetime | None = _created_at()


class PendingAction(SQLModel, table=True):
    """A write proposed by the agent, applied only when the merchant taps "Oui"."""

    __tablename__ = "pending_action"

    id: int | None = Field(default=None, primary_key=True, sa_type=BigInteger)
    shop_id: int = _fk("shop.id")
    user_id: int = _fk("app_user.id")
    kind: str = Field(sa_type=String(48))  # tool name, e.g. propose_sale
    payload: dict = _json(dict)
    status: str = Field(default=PendingStatus.PENDING, sa_type=String(16))
    source_wamid: str | None = None
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    created_at: datetime | None = _created_at()


class ProcessedMessage(SQLModel, table=True):
    __tablename__ = "processed_message"

    wamid: str = Field(primary_key=True)
    received_at: datetime | None = _created_at()


class Receipt(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("shop_id", "number"),)

    id: int | None = Field(default=None, primary_key=True, sa_type=BigInteger)
    shop_id: int = _fk("shop.id")
    entry_id: int = _fk("entry.id")
    number: int  # sequential per shop
    image_key: str
    created_at: datetime | None = _created_at()


class ModelCall(SQLModel, table=True):
    """Every model call with its cost, for the per-merchant cost figure and the global budget."""

    __tablename__ = "model_call"
    __table_args__ = (Index("ix_model_call_created", "created_at"),)

    id: int | None = Field(default=None, primary_key=True, sa_type=BigInteger)
    shop_id: int | None = _fk("shop.id", nullable=True)
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    audio_ms: int = 0
    cost_usd: Decimal = Field(default=Decimal(0), sa_column=Column(Numeric(12, 6), nullable=False))
    created_at: datetime | None = _created_at()


class MessageLog(SQLModel, table=True):
    """The recent conversation, so Kayé understands « et Kofi aussi » or « non, 12 000 ».

    Short-lived context, not an archive: only the last few turns are ever read.
    """

    __tablename__ = "message_log"
    __table_args__ = (Index("ix_message_log_user_created", "user_id", "created_at"),)

    id: int | None = Field(default=None, primary_key=True, sa_type=BigInteger)
    shop_id: int = _fk("shop.id")
    user_id: int = _fk("app_user.id")
    role: str = Field(sa_type=String(16))  # merchant or kaye
    text: str
    created_at: datetime | None = _created_at()
