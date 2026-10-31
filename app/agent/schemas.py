"""Typed arguments of the agent's tools and of vision extractions.

The model fills these; the code validates them with Pydantic, recomputes totals and builds the
confirmation summary itself. Amounts are integer FCFA.
"""

from typing import Any

from pydantic import BaseModel, Field


class SaleLine(BaseModel):
    product: str = Field(description="Product name in the merchant's words, e.g. 'riz'")
    quantity: int = Field(gt=0, description="Number of units, as an integer")
    unit: str | None = Field(
        default=None, description="Local unit if said: tas, bol, sac, demi-sac, tine, boîte, paquet, carton"
    )
    unit_price: int | None = Field(
        default=None, ge=0, description="Price of ONE unit in FCFA, only if the merchant said it"
    )


class ProposeSale(BaseModel):
    """Record a sale. Call it when the merchant says they sold something."""

    lines: list[SaleLine] = Field(min_length=1)
    customer: str | None = Field(default=None, description="Customer name as said; null for anonymous cash sale")
    total: int | None = Field(default=None, ge=0, description="Total in FCFA if the merchant said it")
    paid: int | None = Field(default=None, ge=0, description="Amount paid now in FCFA, if said")
    remaining_debt: int | None = Field(
        default=None, ge=0, description="Amount the customer still owes in FCFA, if said"
    )


class ProposePayment(BaseModel):
    """Record money received from a customer who owed something."""

    customer: str
    amount: int = Field(gt=0, description="Amount received in FCFA")


class ProposeSupplierDebt(BaseModel):
    """Record goods bought from a supplier (grossiste), possibly on credit with a due date."""

    supplier: str = Field(description="Supplier name as said, e.g. 'Koffi'")
    amount: int = Field(gt=0, description="Total in FCFA")
    paid: int | None = Field(default=None, ge=0, description="Amount paid now in FCFA, if said")
    due_date: str | None = Field(default=None, description="Due date as ISO YYYY-MM-DD, if said")
    items: str | None = Field(default=None, description="What was bought, short, e.g. '20 sacs de riz'")


class ProposeSupplierPayment(BaseModel):
    """Record money the merchant paid to a supplier on an existing debt."""

    supplier: str
    amount: int = Field(gt=0)


class ProposeExpense(BaseModel):
    """Record an expense: transport, rent, electricity, bags, wages... money going out."""

    amount: int = Field(gt=0, description="Amount in FCFA")
    label: str = Field(description="What it was for, short, e.g. 'transport'")


class ProposeStockChange(BaseModel):
    """Stock movement not tied to a sale: goods received, lost, spoiled, or a recount.
    Use 'set' when the merchant says how many are left; otherwise 'add' (positive) or 'remove'."""

    product: str
    quantity: int = Field(gt=0)
    mode: str = Field(description="'add', 'remove' or 'set'")
    unit: str | None = None


class AddSeller(BaseModel):
    """Give a seller or apprentice access to record sales. They cannot see totals or debts."""

    phone: str = Field(description="WhatsApp number with country code, e.g. +22890123456")
    name: str | None = None


class CustomerName(BaseModel):
    """A customer or supplier named by the merchant."""

    name: str


class StockQuestion(BaseModel):
    """Ask how much stock is left of a product, or of everything if product is null."""

    product: str | None = None


class SummaryRequest(BaseModel):
    """Ask for the figures of a period: today, yesterday, week or month."""

    period: str = Field(default="today", description="'today', 'yesterday', 'week' or 'month'")


class NoArgs(BaseModel):
    """No arguments."""


class NotebookLine(BaseModel):
    customer: str = Field(description="Name written on the line")
    description: str | None = Field(default=None, description="What was bought, as written")
    amount_owed: int = Field(ge=0, description="Amount still owed in FCFA")
    date: str | None = Field(default=None, description="Date as written, if any")
    unclear: bool = Field(default=False, description="True if the handwriting is hard to read")


class NotebookPage(BaseModel):
    """Debts read from a photo of a handwritten credit notebook page."""

    lines: list[NotebookLine]


class MobileMoneyReceipt(BaseModel):
    """A mobile money payment received, read from a screenshot or SMS."""

    provider: str = Field(description="T-Money, Flooz/Moov Money, or other")
    amount: int = Field(gt=0, description="Amount received in FCFA")
    sender_name: str | None = None
    sender_phone: str | None = None
    reference: str | None = Field(default=None, description="Transaction id / reference")
    date: str | None = None


def inline_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON schema with $defs inlined: simpler for the model and for strict validators."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return resolve(defs[node["$ref"].split("/")[-1]])
            return {k: resolve(v) for k, v in node.items() if k != "title"}
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node

    return resolve(schema)


def tool(name: str, model: type[BaseModel]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": (model.__doc__ or "").strip(),
            "parameters": inline_schema(model),
        },
    }
