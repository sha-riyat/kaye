"""One model call per message: pick a tool, then let the code do the rest."""

import logging

from app.agent import actions
from app.agent.actions import Ctx
from app.agent.prompts import VISION_PROMPT, system_prompt
from app.agent.reply import Reply
from app.agent.schemas import tool
from app.db import queries
from app.models_client import ModelClient, image_part

log = logging.getLogger(__name__)

MAX_TOOL_CALLS = 3
MODEL_PARAMS = {"reasoning_effort": "minimal", "max_tokens": 1500}

TEXT_TOOLS = [
    tool(name, m) for name, m in actions.TOOL_MODELS.items() if name not in ("notebook_page", "mobile_money_receipt")
]
VISION_TOOLS = [tool(n, actions.TOOL_MODELS[n]) for n in ("notebook_page", "mobile_money_receipt")]

# Frequent questions are answered by rules, without paying for a model call.
SHORTCUTS = {
    "bilan": "summary", "mon bilan": "summary", "bilan du jour": "summary",
    "qui me doit": "list_debtors", "qui me doit ?": "list_debtors", "mes debiteurs": "list_debtors",
    "qui je dois payer": "list_supplier_dues", "mes fournisseurs": "list_supplier_dues",
    "stock": "stock_levels", "mon stock": "stock_levels", "le stock": "stock_levels",
    "annule": "propose_correction", "annuler": "propose_correction",
}  # fmt: skip


def shortcut(text: str) -> str | None:
    key = queries.norm(text).rstrip(" ?!.")
    return SHORTCUTS.get(key) or SHORTCUTS.get(key + " ?")


class Agent:
    def __init__(self, models: ModelClient) -> None:
        self.models = models

    async def on_text(self, ctx: Ctx, text: str) -> list[Reply]:
        ctx.text = text
        name = shortcut(text)
        if name:
            return await actions.run_tool(ctx, name, "{}")
        text = await self._with_context(ctx, text)
        contacts = [c.name for c in await _recent_contacts(ctx)]
        messages = [
            {
                "role": "system",
                "content": system_prompt(shop_name=ctx.shop.name, now=ctx.now, contacts=contacts),
            },
            {"role": "user", "content": text},
        ]
        return await self._call(ctx, messages, TEXT_TOOLS)

    async def on_image(self, ctx: Ctx, data: bytes, mime: str, caption: str | None) -> list[Reply]:
        content = [
            {"type": "text", "text": VISION_PROMPT + (f"\nLégende : {caption}" if caption else "")},
            image_part(data, mime),
        ]
        return await self._call(ctx, [{"role": "user", "content": content}], VISION_TOOLS)

    async def _call(self, ctx: Ctx, messages: list[dict], tools: list[dict]) -> list[Reply]:
        response, usage = await self.models.chat(messages=messages, tools=tools, tool_choice="auto", **MODEL_PARAMS)
        await queries.log_model_call(
            ctx.session, shop_id=ctx.shop.id, model=usage.model, tokens_in=usage.tokens_in,
            tokens_out=usage.tokens_out, cost_usd=usage.cost_usd,
        )  # fmt: skip
        message = response.choices[0].message
        calls = (message.tool_calls or [])[:MAX_TOOL_CALLS]
        if not calls:
            return [Reply((message.content or "").strip() or actions.REPHRASE)]
        replies: list[Reply] = []
        for call in calls:
            replies += await actions.run_tool(ctx, call.function.name, call.function.arguments)
        return replies

    async def _with_context(self, ctx: Ctx, text: str) -> str:
        """Fold in the previous exchange when this message is an answer or a correction."""
        pending = await queries.last_clarify(ctx.session, ctx.user.id)
        if pending is not None:
            await queries.settle_pending(ctx.session, pending, actions.PendingStatus.EXPIRED)
            return f"{pending.payload['original']}\nRéponse du commerçant à ma question : {text}"
        corrected = await queries.last_corrected(ctx.session, ctx.user.id)
        if corrected is not None:
            corrected.payload = {**corrected.payload, "corrected": False}
            ctx.session.add(corrected)
            return (
                f"Je t'avais proposé : {actions.describe(corrected)}\n"
                f"Le commerçant corrige : {text}\nRefais la proposition corrigée."
            )
        return text


async def _recent_contacts(ctx: Ctx):
    from sqlmodel import col, select

    from app.db.models import Contact

    query = select(Contact).where(Contact.shop_id == ctx.shop.id).order_by(col(Contact.id).desc()).limit(40)
    return (await ctx.session.exec(query)).all()
