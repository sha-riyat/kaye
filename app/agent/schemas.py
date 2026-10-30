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
    customer: str | None = Field(
        default=None, description="Customer name as said; null for anonymous cash sale"
    )
    total: int | None = Field(default=None, ge=0, description="Total in FCFA if the merchant said it")
    paid: int | None = Field(default=None, ge=0, description="Amount paid now in FCFA, if said")
    remaining_debt: int | None = Field(
        default=None, ge=0, description="Amount the customer still owes in FCFA, if said"
    )


class ProposePayment(BaseModel):
    """Record money received from a customer who owed something."""

    customer: str
    amount: int = Field(gt=0, description="Amount received in FCFA")


class NotebookLine(BaseModel):
    customer: str = Field(description="Name written on the line")
    description: str | None = Field(default=None, description="What was bought, as written")
    amount_owed: int = Field(ge=0, description="Amount still owed in FCFA")
    date: str | None = Field(default=None, description="Date as written, if any")
    unclear: bool = Field(default=False, description="True if the handwriting is hard to read")


class NotebookPage(BaseModel):
    lines: list[NotebookLine]


class MobileMoneyReceipt(BaseModel):
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
