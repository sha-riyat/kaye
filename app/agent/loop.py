"""One model call per message: pick a tool, then let the code do the rest."""

import logging

from app.agent import actions
from app.agent.actions import Ctx
from app.agent.prompts import system_prompt, vision_prompt
from app.agent.reply import Reply
from app.agent.schemas import tool
from app.db import queries
from app.images import prepare_for_reading
from app.models_client import ModelClient, image_part

log = logging.getLogger(__name__)

MAX_TOOL_CALLS = 6
MODEL_PARAMS = {"reasoning_effort": "minimal", "max_tokens": 1500}

TEXT_TOOLS = [
    tool(name, m)
    for name, m in actions.TOOL_MODELS.items()
    if name not in ("notebook_page", "mobile_money_receipt", "shelf_photo")
]
VISION_TOOLS = [
    tool(n, actions.TOOL_MODELS[n]) for n in ("notebook_page", "sales_register", "mobile_money_receipt", "shelf_photo")
]
# Handwriting gets a little reasoning: on a real register page, « low » with the cleaned photo read
# every amount and the date, for about $0.005-0.01 a page (Muse Wonder took over 90 s: too slow).
VISION_PARAMS = {"reasoning_effort": "low", "max_tokens": 4000}

# Frequent questions are answered by rules, without paying for a model call.
SHORTCUTS = {
    "bilan": "summary", "mon bilan": "summary", "bilan du jour": "summary",
    "qui me doit": "list_debtors", "qui me doit ?": "list_debtors", "mes debiteurs": "list_debtors",
    "qui je dois payer": "list_supplier_dues", "mes fournisseurs": "list_supplier_dues",
    "stock": "stock_levels", "mon stock": "stock_levels", "le stock": "stock_levels",
    "annule": "propose_correction", "annuler": "propose_correction",
    "recu": "resend_receipt", "le recu": "resend_receipt", "mon recu": "resend_receipt",
    "renvoie le recu": "resend_receipt",
    "supprimer mes donnees": "erase_my_data", "efface mes donnees": "erase_my_data",
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
            return await actions.merge(ctx, await actions.run_tool(ctx, name, "{}"))
        text = await self._with_context(ctx, text)
        contacts = [c.name for c in await _recent_contacts(ctx)]
        messages = [
            {
                "role": "system",
                "content": system_prompt(shop_name=ctx.shop.name, now=ctx.now, contacts=contacts),
            },
            *await _memory(ctx),
            {"role": "user", "content": text},
        ]
        return await self._call(ctx, messages, TEXT_TOOLS)

    async def on_image(self, ctx: Ctx, data: bytes, mime: str, caption: str | None) -> list[Reply]:
        ctx.image = (data, mime)  # the original, in colour, for SAM
        clean, clean_mime = prepare_for_reading(data)
        content = [
            {"type": "text", "text": vision_prompt(ctx.now) + (f"\nLégende : {caption}" if caption else "")},
            image_part(clean, clean_mime),
        ]
        return await self._call(ctx, [{"role": "user", "content": content}], VISION_TOOLS, VISION_PARAMS)

    async def _call(
        self, ctx: Ctx, messages: list[dict], tools: list[dict], params: dict = MODEL_PARAMS
    ) -> list[Reply]:
        response, usage = await self.models.chat(messages=messages, tools=tools, tool_choice="auto", **params)
        await queries.log_model_call(
            ctx.session, shop_id=ctx.shop.id, model=usage.model, tokens_in=usage.tokens_in,
            tokens_out=usage.tokens_out, cost_usd=usage.cost_usd,
        )  # fmt: skip
        message = response.choices[0].message
        calls = (message.tool_calls or [])[:MAX_TOOL_CALLS]
        if not calls:
            return [Reply((message.content or "").strip() or actions.REPHRASE)]
        names = {c.function.name for c in calls}
        if "summary" in names and names & set(actions.WRITE_TOOLS):
            # « note tout ça et fais-moi le bilan »: the summary must include what is about to be noted
            ctx.summary_after = True
            calls = [c for c in calls if c.function.name != "summary"]
        replies: list[Reply] = []
        for call in calls:
            log.info("tool %s %s", call.function.name, call.function.arguments)
            replies += await actions.run_tool(ctx, call.function.name, call.function.arguments)
        return await actions.merge(ctx, replies)

    async def _with_context(self, ctx: Ctx, text: str) -> str:
        """Fold in the previous exchange when this message is an answer or a correction."""
        questions = await queries.open_questions(ctx.session, ctx.user.id)
        if questions:
            ctx.replaying = True
            for q in questions:
                await queries.settle_pending(ctx.session, q, actions.PendingStatus.EXPIRED)
            asked = " ; ".join(f"« {q.payload.get('question', '')} »" for q in questions)
            return (
                f"{questions[0].payload['original']}\n"
                f"Je lui ai demandé : {asked}\nSa réponse : {text}\n"
                "Les autres opérations de son message sont déjà proposées : traite seulement celles de mes questions."
            )
        corrected = await queries.last_corrected(ctx.session, ctx.user.id)
        if corrected is not None:
            corrected.payload = {**corrected.payload, "corrected": False}
            ctx.session.add(corrected)
            return (
                f"Je t'avais proposé : {actions.describe(corrected)}\n"
                f"Le commerçant corrige : {text}\nRefais la proposition corrigée."
            )
        return text


async def _memory(ctx: Ctx) -> list[dict]:
    """The last turns of the conversation, so a short follow-up is read in context."""
    turns = await queries.recent_turns(ctx.session, ctx.user.id)
    return [{"role": "user" if t.role == "merchant" else "assistant", "content": t.text} for t in turns]


async def _recent_contacts(ctx: Ctx):
    from sqlmodel import col, select

    from app.db.models import Contact

    query = select(Contact).where(Contact.shop_id == ctx.shop.id).order_by(col(Contact.id).desc()).limit(40)
    return (await ctx.session.exec(query)).all()
