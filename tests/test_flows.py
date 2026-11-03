"""End-to-end conversations against a real Postgres, with a scripted model and a fake WhatsApp.

Set TEST_DATABASE_URL (e.g. postgresql://postgres:kaye@127.0.0.1:54329/kaye_test). The model is
scripted so the tests check what the code does with its answers: resolve, compute, confirm, write.
"""

import json
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlmodel import SQLModel, select

from app import router
from app.agent.loop import Agent
from app.agent.reply import Reply
from app.config import Settings
from app.db import ledger
from app.db.engine import Database
from app.db.models import Contact, Entry, PendingAction, Product, Receipt, Shop
from app.models_client import Usage
from app.router import handle_message
from app.services import Services
from app.transcribe import Transcript
from app.webhook import InboundMessage

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")

PHONE = "22890000001"


class FakeModels:
    """Answers each call from a script: a list of (tool_name, args) tuples, or a plain string."""

    def __init__(self) -> None:
        self.script: list = []
        self.calls: list[dict] = []

    def say(self, *answers) -> None:
        self.script.extend(answers)

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        answer = self.script.pop(0)
        if isinstance(answer, tuple):
            answer = [answer]
        if isinstance(answer, str):
            message = SimpleNamespace(content=answer, tool_calls=None)
        else:
            calls = [SimpleNamespace(function=SimpleNamespace(name=n, arguments=json.dumps(a))) for n, a in answer]
            message = SimpleNamespace(content=None, tool_calls=calls)
        response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
        return response, Usage("muse-spark-1.3", 1000, 0, 100)

    async def aclose(self) -> None:
        pass


class FakeWA:
    def __init__(self) -> None:
        self.sent: list[Reply] = []
        self.media = b"IMAGE-BYTES"
        self.blocked: list[str] = []

    def from_number(self, _):
        return self

    async def mark_read(self, _):
        pass

    async def block(self, user):
        self.blocked.append(user)

    async def download_media(self, _):
        return self.media, "image/jpeg"

    async def send_text(self, to, body, reply_to=None):
        self.sent.append(Reply(body))

    async def deliver(self, to, reply, reply_to=None):
        self.sent.append(reply)

    async def aclose(self):
        pass


class FakeTranscriber:
    text = "j'ai vendu du riz"

    language = None

    async def transcribe(self, _, language="French"):
        FakeTranscriber.language = language
        return Transcript(text=self.text, audio_duration_ms=1000)

    async def aclose(self):
        pass


class Chat:
    """One merchant talking to Kayé."""

    def __init__(self, svc: Services, models: FakeModels, wa: FakeWA, sender: str = PHONE) -> None:
        self.svc, self.models, self.wa, self.sender, self.n = svc, models, wa, sender, 0

    async def send(self, type_: str = "text", text: str | None = None, **fields) -> list[Reply]:
        self.n += 1
        msg = InboundMessage(
            wamid=f"wamid.{self.sender}.{self.n}", sender=self.sender, phone_number_id="PNID", profile_name="Afi",
            timestamp=1, type=type_, raw_type=type_, text=text, **fields,
        )  # fmt: skip
        self.wa.sent = []
        await handle_message(msg, self.svc)
        for reply in self.wa.sent:  # amounts use a narrow no-break space; tests read plain spaces
            reply.text = reply.text.replace("\u202f", " ")
        return self.wa.sent

    async def say(self, text: str, *model_answer) -> list[Reply]:
        self.models.say(*model_answer)
        return await self.send(text=text)

    async def tap(self, button_id: str) -> list[Reply]:
        return await self.send("button", text="x", button_id=button_id)

    def last_pending_id(self, replies: list[Reply]) -> int:
        buttons = [b for r in replies for b in r.buttons]
        return int(buttons[0][0].split(":")[1])


@pytest.fixture
async def db():
    database = Database(TEST_DATABASE_URL)
    async with database.engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
    yield database
    await database.dispose()


@pytest.fixture(autouse=True)
def rendered(monkeypatch) -> list[tuple[str, dict]]:
    """Documents drawn during a test, as (template, data); no Chromium."""
    drawn: list[tuple[str, dict]] = []

    async def fake_render(template, data, extra=0):
        drawn.append((template, data))
        return b"\x89PNG-" + template.encode()

    monkeypatch.setattr(router, "render_png", fake_render)
    return drawn


@pytest.fixture
def models():
    return FakeModels()


@pytest.fixture
async def chat(db, models):
    settings = Settings(_env_file=None, daily_message_quota_per_user=100, global_daily_model_budget_usd=5.0)
    wa = FakeWA()
    svc = Services(settings, wa, FakeTranscriber(), db, Agent(models), storage=None)
    c = Chat(svc, models, wa)
    await c.send(text="Bonjour")  # language
    await c.tap("lang:fr")  # welcome
    await c.send(text="Chez Afi")  # shop name
    return c


async def contact_named(db, name: str) -> Contact | None:
    async with db.session() as s:
        return (await s.exec(select(Contact).where(Contact.name == name))).first()


async def balance(db, name: str) -> int:
    contact = await contact_named(db, name)
    async with db.session() as s:
        return await ledger.contact_balance(s, shop_id=contact.shop_id, contact_id=contact.id)


SALE = ("propose_sale", {"lines": [{"product": "riz", "quantity": 3, "unit": "sac", "unit_price": 11_000}],
                         "customer": "Ama Koudjo", "paid": 25_000})  # fmt: skip


# --- onboarding ---


async def test_onboarding_names_the_shop(db, models):
    settings = Settings(_env_file=None)
    wa = FakeWA()
    svc = Services(settings, wa, FakeTranscriber(), db, Agent(models), storage=None)
    c = Chat(svc, models, wa)
    first = await c.send(text="Bonjour")
    assert first[0].buttons == [("lang:fr", "Français"), ("lang:en", "English")]
    welcome = await c.tap("lang:fr")
    assert len(welcome) == 1
    assert "Quel nom je mets sur vos reçus" in welcome[0].text and "démo" in welcome[0].text
    assert welcome[0].buttons == [("name:profile", "Afi")]  # the WhatsApp profile name, one tap
    named = await c.send(text="Chez Afi")
    assert "Chez Afi" in named[0].text
    assert [b for b, _ in named[0].buttons] == ["start:demo", "start:voice", "start:photo"]
    async with db.session() as s:
        assert (await s.exec(select(Shop))).one().name == "Chez Afi"
    assert models.calls == []  # onboarding never costs a model call


async def test_the_profile_name_button_names_the_business(db, models):
    wa = FakeWA()
    c = Chat(Services(Settings(_env_file=None), wa, FakeTranscriber(), db, Agent(models), None), models, wa)
    await c.send(text="Bonjour")
    await c.tap("lang:fr")
    named = await c.tap("name:profile")
    assert "Afi" in named[0].text
    async with db.session() as s:
        assert (await s.exec(select(Shop))).one().name == "Afi"


async def test_the_example_sale_sends_a_receipt_and_writes_nothing(chat, db, rendered):
    recap = await chat.tap("start:demo")
    assert "Vente à Ama" in recap[0].text and recap[0].buttons[0] == ("demo:ok", "Oui, noter")
    done = await chat.tap("demo:ok")
    assert done[0].image and "À vous" in done[1].text
    template, data = rendered[-1]
    assert template == "recu_ticket.html.j2" and data["number"] == "EXEMPLE" and data["due"] == 8_000
    assert data["shop"]["name"] == "Chez Afi"
    async with db.session() as s:
        assert (await s.exec(select(Entry))).all() == []
        assert (await s.exec(select(Receipt))).all() == []
    assert chat.models.calls == []


async def test_the_voice_and_photo_buttons_explain_and_help_lists_everything(chat):
    assert "micro" in (await chat.tap("start:voice"))[0].text
    assert "photo" in (await chat.tap("start:photo"))[0].text
    help_ = await chat.send(text="aide")
    assert "Qui me doit" in help_[0].text and "crée mon logo" in help_[0].text
    assert chat.models.calls == []


async def test_a_first_timer_is_shown_where_to_tap_until_the_first_entry(chat):
    first = await chat.say("vente", SALE)
    assert "Appuyez sur « Oui, noter »" in first[0].text
    await chat.tap(first[0].buttons[0][0])
    second = await chat.say("vente", SALE)
    assert "Appuyez sur" not in second[0].text


async def test_a_silent_newcomer_is_nudged_once(db, models, monkeypatch):
    from app import jobs
    from app.db import queries

    wa = FakeWA()
    svc = Services(Settings(_env_file=None), wa, FakeTranscriber(), db, Agent(models), None)
    named = Chat(svc, models, wa, sender="22890000002")
    await named.send(text="Bonjour")
    await named.tap("lang:fr")
    await named.send(text="Ben boutique")
    unnamed = Chat(svc, models, wa, sender="22990000003")
    await unnamed.send(text="Bonjour")
    await unnamed.tap("lang:fr")
    later = datetime.now(UTC) + timedelta(hours=2)
    monkeypatch.setattr(queries, "utcnow", lambda: later)
    wa.sent = []
    await jobs.run_hourly(svc)
    texts = [m.text for m in wa.sent]
    assert len(texts) == 2
    assert any("J'ai vendu 2 savons" in t for t in texts) and any("Quel nom" in t for t in texts)
    wa.sent = []
    await jobs.run_hourly(svc)
    assert wa.sent == []  # once only


async def test_a_blocked_number_gets_no_reply_and_no_shop(db, models):
    wa = FakeWA()
    settings = Settings(_env_file=None, blocked_numbers="+22990000000, 22991111111")
    c = Chat(Services(settings, wa, FakeTranscriber(), db, Agent(models), None), models, wa)
    c.sender = "22991111111"
    assert await c.send(text="Bonjour") == []
    assert wa.blocked == ["22991111111"]
    async with db.session() as s:
        assert (await s.exec(select(Shop))).all() == []


async def test_an_overlong_shop_name_is_asked_again(db, models):
    wa = FakeWA()
    c = Chat(Services(Settings(_env_file=None), wa, FakeTranscriber(), db, Agent(models), None), models, wa)
    await c.send(text="Bonjour")
    await c.tap("lang:fr")
    again = await c.send(text="x" * 200)
    assert "quel nom je mets sur vos reçus" in again[0].text.lower()


# --- sales ---


async def test_credit_sale_needs_a_yes_then_sends_a_receipt(chat, db):
    replies = await chat.say("j'ai vendu 3 sacs de riz à Ama, 25 000 reçus", SALE)
    assert "Vente à Ama Koudjo" in replies[0].text
    assert "33 000" in replies[0].text and "Reste dû" in replies[0].text and "8 000" in replies[0].text
    assert [b[1] for b in replies[0].buttons] == ["Oui, noter", "Corriger", "Annuler"]
    assert await contact_named(db, "Ama Koudjo") is None  # nothing written before "Oui"

    done = await chat.tap(replies[0].buttons[0][0])
    assert "Ama Koudjo vous doit 8" in done[0].text
    assert done[1].image and "Reçu n° 0001" in done[1].text
    assert await balance(db, "Ama Koudjo") == 8_000


async def test_the_model_cannot_set_a_wrong_total(chat):
    sale = (
        "propose_sale",
        {"lines": [{"product": "riz", "quantity": 3, "unit_price": 11_000}], "total": 30_000, "walk_in": True},
    )
    replies = await chat.say("3 riz à 11 000, total 30 000", sale)
    assert "Total : *33 000" in replies[0].text
    assert "30 000" in replies[0].text and "calcul donne" in replies[0].text


async def test_double_tap_on_yes_writes_once(chat, db):
    replies = await chat.say("vente", SALE)
    yes = replies[0].buttons[0][0]
    await chat.tap(yes)
    again = await chat.tap(yes)
    assert "déjà été traitée" in again[0].text
    async with db.session() as s:
        assert len((await s.exec(select(Entry))).all()) == 1


async def test_cancel_writes_nothing(chat, db):
    replies = await chat.say("vente", SALE)
    cancelled = await chat.tap(replies[0].buttons[2][0])
    assert "Rien n'est noté" in cancelled[0].text
    async with db.session() as s:
        assert (await s.exec(select(Entry))).all() == []


async def test_an_expired_proposal_is_refused(chat, db):
    replies = await chat.say("vente", SALE)
    async with db.engine.begin() as conn:
        await conn.execute(text("update pending_action set expires_at = now() - interval '1 minute'"))
    expired = await chat.tap(replies[0].buttons[0][0])
    assert "plus valable" in expired[0].text
    async with db.session() as s:
        assert (await s.exec(select(Entry))).all() == []


async def test_correct_button_replays_the_proposal_with_the_fix(chat, models):
    replies = await chat.say("vente", SALE)
    asked = await chat.tap(replies[0].buttons[1][0])
    assert "ce qu'il faut changer" in asked[0].text
    fixed = ("propose_sale", {"lines": [{"product": "riz", "quantity": 3, "unit": "sac", "unit_price": 12_000}],
                             "customer": "Ama Koudjo", "paid": 25_000})  # fmt: skip
    again = await chat.say("non, 12 000 le sac", fixed)
    sent_to_model = models.calls[-1]["messages"][-1]["content"]
    assert "Vente à Ama Koudjo" in sent_to_model and "12 000 le sac" in sent_to_model
    assert "36 000" in again[0].text


async def test_a_missing_price_is_asked_then_remembered(chat, models):
    no_price = ("propose_sale", {"lines": [{"product": "huile", "quantity": 2}], "customer": "Kofi"})
    asked = await chat.say("2 huile à Kofi", no_price)
    assert asked[0].text == "Quel est le prix de huile, à l'unité ?" and asked[0].buttons == []
    priced = ("propose_sale", {"lines": [{"product": "huile", "quantity": 2, "unit_price": 6_500}], "customer": "Kofi"})
    replies = await chat.say("6 500 pièce", priced)
    assert "2 huile × 6 500 = 13 000" in replies[0].text
    assert "2 huile à Kofi" in models.calls[-1]["messages"][-1]["content"]  # the first message came along


async def test_usual_price_is_learned_from_a_confirmed_sale(chat):
    first = await chat.say("vente", SALE)
    await chat.tap(first[0].buttons[0][0])
    no_price = (
        "propose_sale",
        {"lines": [{"product": "riz", "quantity": 2, "unit": "sac"}], "customer": "Kofi", "paid": 22_000},
    )
    replies = await chat.say("2 sacs de riz à Kofi", no_price)
    assert "2 sacs riz × 11 000 = 22 000" in replies[0].text


async def test_ambiguous_customer_is_asked_with_a_list(chat, db):
    line = {"product": "riz", "quantity": 1, "unit_price": 1_000}
    first = await chat.say("vente", ("propose_sale", {"lines": [line], "customer": "Ama Koudjo"}))
    await chat.tap(first[0].buttons[0][0])
    # a second Ama who shares only a first name is never merged silently
    second = await chat.say("vente", ("propose_sale", {"lines": [line], "customer": "Ama Mensah"}))
    assert "plusieurs" in second[0].text
    confirm = await chat.tap(next(b[0] for b in second[0].buttons if b[0].endswith("new")))
    await chat.tap(confirm[0].buttons[0][0])
    sale = (
        "propose_sale",
        {"lines": [{"product": "riz", "quantity": 1, "unit_price": 1_000}], "customer": "Ama", "paid": 0},
    )
    asked = await chat.say("riz à Ama, elle doit", sale)
    assert "plusieurs" in asked[0].text
    ids = [b[0] for b in asked[0].buttons]
    assert len(ids) == 3  # two candidates and "new"
    picked_id = next(i for i in ids if not i.endswith("new"))
    confirmation = await chat.tap(picked_id)
    assert "Vente à" in confirmation[0].text and confirmation[0].buttons[0][1] == "Oui, noter"


async def test_a_spoken_nickname_is_learned_once_confirmed(chat, db):
    def sale(name):
        line = {"product": "riz", "quantity": 1, "unit_price": 1_000}
        return ("propose_sale", {"lines": [line], "customer": name, "paid": 0})

    first = await chat.say("vente", sale("Ama Koudjo"))
    await chat.tap(first[0].buttons[0][0])
    asked = await chat.say("vente", sale("Ama du marché"))  # shares a word: never merged silently
    assert "plusieurs" in asked[0].text
    picked = await chat.tap(next(b[0] for b in asked[0].buttons if not b[0].endswith("new")))
    await chat.tap(picked[0].buttons[0][0])
    assert "Ama du marché" in (await contact_named(db, "Ama Koudjo")).aliases
    again = await chat.say("vente", sale("Ama du marché"))
    assert "Vente à Ama Koudjo" in again[0].text  # now recognised at once


async def test_a_shortened_name_is_taken_for_the_known_contact(chat):
    line = {"product": "riz", "quantity": 1, "unit_price": 1_000}
    first = await chat.say("vente", ("propose_sale", {"lines": [line], "customer": "Ama Koudjo", "paid": 0}))
    await chat.tap(first[0].buttons[0][0])
    second = await chat.say("vente", ("propose_sale", {"lines": [line], "customer": "Ama", "paid": 0}))
    assert "Vente à Ama Koudjo" in second[0].text and "nouveau" not in second[0].text


# --- payments, mobile money, notebook ---


async def test_payment_settles_a_debt(chat, db):
    sale = await chat.say("vente", SALE)
    await chat.tap(sale[0].buttons[0][0])
    pay = ("propose_payment", {"customer": "Ama", "amount": 8_000})
    replies = await chat.say("Ama a payé 8 000", pay)
    assert "Dette : 8 000 → *0*" in replies[0].text
    done = await chat.tap(replies[0].buttons[0][0])
    assert "soldée" in done[0].text
    assert await balance(db, "Ama Koudjo") == 0


MOMO = (
    "mobile_money_receipt",
    {"provider": "T-Money", "amount": 8_000, "sender_name": "Ama Koudjo", "reference": "TM123"},
)


async def test_mobile_money_screenshot_pays_the_debt_once(chat, db):
    sale = await chat.say("vente", SALE)
    await chat.tap(sale[0].buttons[0][0])
    chat.models.say(MOMO)
    replies = await chat.send("image", media_id="M1")
    assert "T-Money" in replies[0].text and "Dette : 8 000" in replies[0].text
    await chat.tap(replies[0].buttons[0][0])
    assert await balance(db, "Ama Koudjo") == 0
    chat.models.say(MOMO)
    duplicate = await chat.send("image", media_id="M2")
    assert "déjà noté" in duplicate[0].text


async def test_notebook_photo_imports_debts_after_one_yes(chat, db):
    page = ("notebook_page", {"lines": [
        {"customer": "Ama", "amount_owed": 15_000, "description": "riz"},
        {"customer": "Komlan", "amount_owed": 5_000, "unclear": True},
    ]})  # fmt: skip
    chat.models.say(page)
    replies = await chat.send("image", media_id="M1")
    assert "2 dette(s)" in replies[0].text and "❓ Komlan" in replies[0].text and "20 000" in replies[0].text
    await chat.tap(replies[0].buttons[0][0])
    assert await balance(db, "Ama") == 15_000 and await balance(db, "Komlan") == 5_000


# --- suppliers, expenses, stock ---


async def test_a_delivery_is_one_recap_with_one_set_of_buttons(chat, db):
    debt = (
        "propose_supplier_debt",
        {"supplier": "Koffi", "amount": 180_000, "due_date": "2026-11-06", "items": "20 sacs de riz"},
    )
    stock = ("propose_stock_change", {"product": "riz", "quantity": 20, "mode": "add", "unit": "sac"})
    chat.models.say([debt, stock])
    replies = await chat.send(text="Koffi a livré 20 sacs de riz, 180 000, je paie vendredi")
    assert len(replies) == 1
    recap = replies[0].text
    assert "Achat chez Koffi" in recap and "06/11/2026" in recap and "0 → *20*" in recap
    assert "\n\nJe note tout ?" in recap and len(replies[0].buttons) == 3
    done = await chat.tap(replies[0].buttons[0][0])
    assert len(done) == 1 and done[0].text.count("C'est noté") == 1
    assert "• Vous devez 180 000 FCFA à Koffi" in done[0].text and "• Stock de riz : *20*" in done[0].text
    assert await balance(db, "Koffi") == 180_000
    due = await chat.send(text="qui je dois payer ?")
    assert "Koffi : *180 000" in due[0].text and "06/11" in due[0].text


async def test_cancelling_a_grouped_recap_writes_nothing(chat, db):
    stock = ("propose_stock_change", {"product": "riz", "quantity": 20, "mode": "add"})
    expense = ("propose_expense", {"amount": 3_500, "label": "transport"})
    chat.models.say([stock, expense])
    replies = await chat.send(text="reçu 20 riz, transport 3 500")
    await chat.tap(replies[0].buttons[2][0])
    async with db.session() as s:
        assert (await s.exec(select(Entry))).all() == []
        assert all(p.status == "cancelled" for p in (await s.exec(select(PendingAction))).all())


async def test_sales_lower_tracked_stock_and_warn_when_low(chat, db):
    start = await chat.say(
        "j'ai 5 sacs de riz", ("propose_stock_change", {"product": "riz", "quantity": 5, "mode": "set", "unit": "sac"})
    )
    await chat.tap(start[0].buttons[0][0])
    sale = (
        "propose_sale",
        {"lines": [{"product": "riz", "quantity": 3, "unit": "sac", "unit_price": 11_000}], "customer": "Ama"},
    )
    replies = await chat.say("3 riz à Ama", sale)
    done = await chat.tap(replies[0].buttons[0][0])
    assert "Il ne reste que 2 riz" in done[0].text
    async with db.session() as s:
        assert (await s.exec(select(Product))).one().stock == 2


async def test_untracked_products_do_not_go_negative(chat, db):
    replies = await chat.say("vente", SALE)
    await chat.tap(replies[0].buttons[0][0])
    async with db.session() as s:
        assert (await s.exec(select(Product).where(Product.name == "riz"))).one().stock is None


async def test_stock_question_is_answered_by_code(chat, models):
    await chat.say(
        "j'ai 2 bidons d'huile", ("propose_stock_change", {"product": "huile", "quantity": 2, "mode": "set"})
    )
    pending = await chat.send(text="stock")  # shortcut, no model call
    assert pending[0].text.startswith("Je ne suis encore aucun stock") or "huile" in pending[0].text


async def test_expense_and_cash_in_the_daily_summary(chat, rendered):
    sale = await chat.say("vente", SALE)
    await chat.tap(sale[0].buttons[0][0])
    spend = await chat.say("transport 3 500", ("propose_expense", {"amount": 3_500, "label": "transport"}))
    assert "Dépense : transport" in spend[0].text
    await chat.tap(spend[0].buttons[0][0])
    calls_before = len(chat.models.calls)
    bilan = await chat.send(text="bilan")  # shortcut: no model call
    assert len(chat.models.calls) == calls_before
    assert bilan[0].image and bilan[0].text == "*Bilan du jour* · ventes 33 000 FCFA · en caisse 21 500 FCFA"
    template, data = rendered[-1]
    assert template == "bilan.html.j2" and data["title"] == "Bilan du jour"
    assert (data["sales"], data["credit"], data["expenses"]) == (33_000, 8_000, 3_500)
    assert data["cash_in_hand"] == 21_500  # 25 000 cashed - 3 500 expense
    assert data["outstanding"] == 8_000 and data["debtors"][0]["name"] == "Ama Koudjo"


async def test_summary_text_without_an_image_when_nothing_to_draw_or_render_fails(chat, monkeypatch):
    empty = await chat.send(text="bilan")
    assert empty[0].image is None and "Aucune opération notée" in empty[0].text
    sale = await chat.say("vente", SALE)
    await chat.tap(sale[0].buttons[0][0])

    async def broken(*_):
        raise router.RenderError("no Chromium found")

    monkeypatch.setattr(router, "render_png", broken)
    fallback = await chat.send(text="bilan")
    assert fallback[0].image is None
    assert "Ventes : *33 000" in fallback[0].text and "À encaisser : *8 000" in fallback[0].text


async def test_whos_in_debt_and_a_ready_reminder(chat, db):
    sale = await chat.say("vente", SALE)
    await chat.tap(sale[0].buttons[0][0])
    async with db.session() as s:
        ama = (await s.exec(select(Contact))).one()
        ama.phone = "+22890123456"
        s.add(ama)
    debtors = await chat.send(text="qui me doit ?")
    assert "Ama Koudjo : *8 000" in debtors[0].text and debtors[0].buttons[0][1].startswith("Relancer")
    reminder = await chat.tap(debtors[0].buttons[0][0])
    assert "il reste 8 000 FCFA chez Chez Afi" in reminder[0].text
    assert reminder[0].link.startswith("https://wa.me/22890123456?text=")


async def test_undo_the_last_operation_restores_everything(chat, db):
    sale = await chat.say("vente", SALE)
    await chat.tap(sale[0].buttons[0][0])
    undo = await chat.send(text="annule")  # shortcut
    assert "Annuler cette opération" in undo[0].text and "Vente · Ama Koudjo" in undo[0].text
    await chat.tap(undo[0].buttons[0][0])
    assert await balance(db, "Ama Koudjo") == 0
    async with db.session() as s:
        assert len((await s.exec(select(Entry))).all()) == 2  # the sale and its reversal: nothing deleted


# --- sellers, voice, limits ---


async def test_a_seller_can_sell_but_not_see_the_books(chat, db, models):
    add = await chat.say(
        "ajoute mon vendeur Kodjo +228 91 11 22 33", ("add_seller", {"phone": "+228 91 11 22 33", "name": "Kodjo"})
    )
    assert "Ajouter Kodjo comme vendeur" in add[0].text
    await chat.tap(add[0].buttons[0][0])
    seller = Chat(chat.svc, models, chat.wa, sender="22891112233")
    refused = await seller.send(text="qui me doit ?")  # a shortcut, still refused
    assert "réservée au patron" in refused[0].text
    sale = await seller.say("vente", SALE)
    assert "Vente à Ama Koudjo" in sale[0].text
    done = await seller.tap(sale[0].buttons[0][0])
    assert "C'est noté" in done[0].text
    async with db.session() as s:
        assert (await s.exec(select(Entry))).one().created_by is not None


async def test_voice_note_goes_straight_to_the_recap(chat):
    chat.models.say(SALE)
    replies = await chat.send("audio", media_id="A1")
    assert len(replies) == 1 and "Vente à Ama Koudjo" in replies[0].text  # no « J'ai compris » echo
    assert chat.models.calls[-1]["messages"][-1]["content"] == FakeTranscriber.text


async def test_logo_caption_is_not_read_as_a_notebook(chat, models):
    replies = await chat.send("image", text="mon logo", media_id="L1")
    assert "logo" in replies[0].text.lower()
    assert models.calls == []


async def test_daily_quota_blocks_the_model_but_not_buttons(chat, db):
    chat.svc.settings.daily_message_quota_per_user = 1
    chat.models.say("Bonjour !")
    await chat.send(text="salut")
    blocked = await chat.send(text="encore")
    assert "reprends demain" in blocked[0].text
    assert len(chat.models.calls) == 1


async def test_chitchat_gets_a_short_reply_and_no_write(chat, db):
    replies = await chat.say("merci Kayé", "Avec plaisir ! 🙏")
    assert replies[0].text == "Avec plaisir ! 🙏"
    async with db.session() as s:
        assert (await s.exec(select(PendingAction))).all() == []


async def test_invalid_tool_arguments_ask_to_rephrase(chat):
    replies = await chat.say("vends", ("propose_sale", {"lines": []}))
    assert "pas bien compris" in replies[0].text


async def test_model_cost_is_logged_per_call(chat, db):
    await chat.say("salut", "Bonjour !")
    async with db.session() as s:
        from app.db.models import ModelCall

        calls = (await s.exec(select(ModelCall))).all()
        assert len(calls) == 1 and float(calls[0].cost_usd) > 0 and calls[0].shop_id is not None


# --- scheduled jobs ---


async def test_evening_summary_and_supplier_reminder_are_sent(chat, db, monkeypatch):
    from datetime import UTC, datetime

    from app import jobs
    from app.db import queries

    sale = await chat.say("vente", SALE)
    await chat.tap(sale[0].buttons[0][0])
    debt = ("propose_supplier_debt", {"supplier": "Koffi", "amount": 90_000, "due_date": "2026-11-01"})
    r = await chat.say("Koffi 90 000", debt)
    await chat.tap(r[0].buttons[0][0])
    fixed_now = datetime.now(UTC).replace(hour=8)  # the supplier-reminder hour
    monkeypatch.setattr(queries, "utcnow", lambda: fixed_now)
    async with db.session() as s:
        shop = (await s.exec(select(Shop))).one()
        shop.summary_hour = 8
        s.add(shop)
    chat.wa.sent = []
    await jobs.run_hourly(chat.svc)
    assert any(m.image and m.text.startswith("*Bilan du jour*") for m in chat.wa.sent)
    texts = [m.text for m in chat.wa.sent]
    assert any("Rappel fournisseurs" in t and "Koffi" in t for t in texts)


# --- lessons from the first live test ---


async def test_a_missing_price_is_asked_inside_the_recap_and_never_twice(chat, db):
    no_price = ("propose_sale", {"lines": [{"product": "riz", "quantity": 4, "unit": "sac"}], "customer": "Ama"})
    expense = ("propose_expense", {"amount": 3_500, "label": "transport"})
    first = await chat.say("4 sacs à Ama, transport 3 500", [no_price, expense])
    assert len(first) == 1
    assert "Dépense : transport" in first[0].text and "❓ Quel est le prix pour 1 sac de riz ?" in first[0].text
    await chat.tap(first[0].buttons[0][0])  # the expense can be noted right away
    priced = (
        "propose_sale",
        {"lines": [{"product": "riz", "quantity": 4, "unit": "sac", "unit_price": 11_000}], "customer": "Ama"},
    )
    second = await chat.say("11 000 le sac", [priced, expense])  # the model repeats the expense
    assert len(second) == 1 and "Vente à Ama" in second[0].text and "Dépense" not in second[0].text
    assert "traite seulement celles de mes questions" in chat.models.calls[-1]["messages"][-1]["content"]


async def test_supplier_delivery_without_amount_asks_how_much(chat):
    debt = ("propose_supplier_debt", {"supplier": "Koffi", "items": "20 sacs de riz"})
    replies = await chat.say("reçu 20 sacs chez Koffi, je paie vendredi", debt)
    assert replies[0].text == "Combien devez-vous à Koffi pour 20 sacs de riz ?"


async def test_products_are_matched_exactly_not_by_substring(chat, db):
    a = await chat.say(
        "j'ai 5 sacs de riz parfumé", ("propose_stock_change", {"product": "riz parfumé", "quantity": 5, "mode": "set"})
    )
    await chat.tap(a[0].buttons[0][0])
    b = await chat.say(
        "reçu 20 sacs de riz", ("propose_stock_change", {"product": "riz", "quantity": 20, "mode": "add"})
    )
    assert "0 → *20*" in b[0].text  # plain rice is not the perfumed one
    await chat.tap(b[0].buttons[0][0])
    async with db.session() as s:
        assert sorted((p.name, p.stock) for p in (await s.exec(select(Product))).all()) == [
            ("riz", 20),
            ("riz parfumé", 5),
        ]


async def test_two_open_questions_come_in_one_message_and_are_answered_together(chat, models):
    no_price = ("propose_sale", {"lines": [{"product": "riz", "quantity": 4, "unit": "sac"}], "customer": "Ama"})
    no_amount = ("propose_supplier_debt", {"supplier": "Koffi"})
    asked = await chat.say("vendu 4 sacs à Ama, reçu du riz de Koffi", [no_price, no_amount])
    assert len(asked) == 1 and "Quel est le prix" in asked[0].text and "Combien devez-vous à Koffi" in asked[0].text
    await chat.say("11 000 le sac, et je dois 180 000 à Koffi", "ok")
    sent = models.calls[-1]["messages"][-1]["content"]
    assert "Quel est le prix pour 1 sac de riz" in sent and "Combien devez-vous à Koffi" in sent


async def test_recent_turns_are_given_to_the_model(chat, models):
    await chat.say("salut", "Bonjour ! Que puis-je noter ?")
    await chat.say("et Kofi aussi", "D'accord")
    history = models.calls[-1]["messages"][1:-1]
    assert {"role": "user", "content": "salut"} in history
    assert {"role": "assistant", "content": "Bonjour ! Que puis-je noter ?"} in history


async def test_a_summary_asked_with_operations_comes_after_the_yes(chat, rendered):
    expense = ("propose_expense", {"amount": 5_000, "label": "transport"})
    recap = await chat.say("transport 5 000 et fais-moi le bilan", [SALE, expense, ("summary", {"period": "today"})])
    assert len(recap) == 1 and "bilan suivra" in recap[0].text
    done = await chat.tap(recap[0].buttons[0][0])
    assert done[-1].image and done[-1].text.startswith("*Bilan du jour* · ventes 33 000")
    template, data = rendered[-1]
    assert template == "bilan.html.j2" and data["expenses"] == 5_000  # the summary includes what was just noted


async def test_a_receipt_can_be_asked_again_with_the_same_number(chat):
    sale = await chat.say("vente", SALE)
    first = await chat.tap(sale[0].buttons[0][0])
    assert "Reçu n° 0001" in first[1].text
    again = await chat.send(text="reçu")  # shortcut
    assert again[0].image and "Reçu n° 0001 pour Ama Koudjo" in again[0].text
    by_name = await chat.say("renvoie le reçu d'Ama", ("resend_receipt", {"customer": "Ama"}))
    assert "Reçu n° 0001" in by_name[0].text


async def test_an_unnamed_sale_asks_who_bought_before_any_receipt(chat, db):
    unnamed = ("propose_sale", {"lines": [{"product": "chargeurs", "quantity": 25, "unit_price": 1_500},
                                          {"product": "Samsung", "quantity": 1, "unit_price": 80_000}]})  # fmt: skip
    asked = await chat.say("vendu 25 chargeurs et un Samsung", unnamed)
    assert (
        asked[0].text
        == "À qui avez-vous vendu 25 chargeurs, 1 Samsung ? Un seul client, plusieurs, ou un client de passage ?"
    )
    assert asked[0].buttons == []
    to_kossi = (
        "propose_sale",
        {"lines": [{"product": "chargeurs", "quantity": 25, "unit_price": 1_500}], "customer": "Kossi"},
    )
    to_ama = (
        "propose_sale",
        {"lines": [{"product": "Samsung", "quantity": 1, "unit_price": 80_000}], "customer": "Ama"},
    )
    recap = await chat.say("les chargeurs à Kossi, le Samsung à Ama", [to_kossi, to_ama])
    assert len(recap) == 1 and "Vente à Kossi" in recap[0].text and "Vente à Ama" in recap[0].text
    done = await chat.tap(recap[0].buttons[0][0])
    receipts = [r for r in done if r.image]
    assert len(receipts) == 2 and "pour Kossi" in receipts[0].text and "pour Ama" in receipts[1].text


async def test_a_walk_in_sale_needs_no_name(chat):
    walk_in = ("propose_sale", {"lines": [{"product": "pain", "quantity": 2, "unit_price": 250}], "walk_in": True})
    recap = await chat.say("2 pains, client de passage", walk_in)
    assert "Vente · client de passage" in recap[0].text and recap[0].buttons


# --- SAM stock counting and Muse Image logos ---


class FakeMedia:
    def __init__(self, count: int = 9) -> None:
        self.n, self.nouns = count, []

    async def count(self, image, mime, noun):
        self.nouns.append(noun)
        return self.n

    async def logos(self, prompt, n=3):
        return [f"PNG{i}".encode() for i in range(n)]

    async def aclose(self):
        pass


class FakeStorage:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    async def put(self, key, data, content_type):
        self.files[key] = data

    async def get(self, key):
        return self.files[key]


async def test_a_shelf_photo_is_counted_by_sam_then_confirmed(chat, db):
    chat.svc.media = FakeMedia(9)
    chat.models.say(("shelf_photo", {"product": "riz", "unit": "sac", "object_en": "sack"}))
    replies = await chat.send("image", media_id="S1")
    assert "Stock compté sur la photo : riz" in replies[0].text and "J'en vois 9 sac" in replies[0].text
    assert chat.svc.media.nouns == ["sack"]
    await chat.tap(replies[0].buttons[0][0])
    async with db.session() as s:
        assert (await s.exec(select(Product))).one().stock == 9


async def test_create_logo_offers_three_and_keeps_the_chosen_one(chat, db):
    chat.svc.media, chat.svc.storage = FakeMedia(), FakeStorage()
    replies = await chat.say("crée mon logo", ("create_logo", {}))
    assert [r.text for r in replies[:3]] == ["Logo 1", "Logo 2", "Logo 3"] and all(r.image for r in replies[:3])
    chosen = await chat.tap(replies[3].buttons[1][0])
    assert "C'est votre logo" in chosen[0].text
    async with db.session() as s:
        key = (await s.exec(select(Shop))).one().logo_key
    assert chat.svc.storage.files[key] == b"PNG1"


async def test_erase_my_data_wipes_everything_after_a_yes(chat, db):
    sale = await chat.say("vente", SALE)
    await chat.tap(sale[0].buttons[0][0])
    asked = await chat.send(text="supprimer mes données")  # shortcut
    assert "Supprimer toutes vos données" in asked[0].text
    done = await chat.tap(asked[0].buttons[0][0])
    assert "toutes vos données sont effacées" in done[0].text
    async with db.session() as s:
        assert (await s.exec(select(Entry))).all() == [] and (await s.exec(select(Contact))).all() == []
        assert (await s.exec(select(Shop))).all() == []
    again = await chat.send(text="Bonjour")
    assert "quelle langue" in again[0].text.lower()  # a first contact again: the language comes first


async def test_a_greeting_is_never_taken_as_the_shop_name(db, models):
    wa = FakeWA()
    c = Chat(Services(Settings(_env_file=None), wa, FakeTranscriber(), db, Agent(models), None), models, wa)
    await c.send(text="Bonjour")
    await c.tap("lang:fr")
    again = await c.send(text="Salut !")
    assert "quel nom je mets sur vos reçus" in again[0].text.lower()


# --- documents drawn as images ---


async def test_paying_off_a_debt_sends_a_quittance(chat, rendered):
    sale = await chat.say("vente", SALE)
    await chat.tap(sale[0].buttons[0][0])  # receipt 0001, Ama owes 8 000
    pay = await chat.say("Ama a payé 8 000", ("propose_payment", {"customer": "Ama", "amount": 8_000}))
    done = await chat.tap(pay[0].buttons[0][0])
    assert "Sa dette est soldée" in done[0].text
    assert done[-1].image and done[-1].text.startswith("Quittance pour Ama Koudjo")
    template, data = rendered[-1]
    assert template == "quittance.html.j2" and (data["number"], data["before"], data["amount"]) == (
        "0002",
        8_000,
        8_000,
    )


async def test_a_partial_payment_sends_no_quittance(chat, rendered):
    sale = await chat.say("vente", SALE)
    await chat.tap(sale[0].buttons[0][0])
    pay = await chat.say("Ama a payé 3 000", ("propose_payment", {"customer": "Ama", "amount": 3_000}))
    done = await chat.tap(pay[0].buttons[0][0])
    assert len(done) == 1 and "Il reste 5 000" in done[0].text
    assert all(t != "quittance.html.j2" for t, _ in rendered)


async def test_reminder_and_statement_are_drawn(chat, rendered):
    sale = await chat.say("vente", SALE)
    await chat.tap(sale[0].buttons[0][0])
    debtors = await chat.send(text="qui me doit ?")
    reminder = await chat.tap(debtors[0].buttons[0][0])
    assert reminder[0].image and "il reste 8 000 FCFA chez Chez Afi" in reminder[0].text
    template, data = rendered[-1]
    assert template == "rappel.html.j2" and data["due"] == 8_000
    assert data["open_items"][0]["receipt"] == "0001" and data["open_items"][0]["label"].startswith("Achat du")
    pay = await chat.say("Ama a payé 3 000", ("propose_payment", {"customer": "Ama", "amount": 3_000}))
    await chat.tap(pay[0].buttons[0][0])
    statement = await chat.say("relevé d'Ama", ("customer_statement", {"name": "Ama"}))
    assert statement[0].image and statement[0].text.startswith("Relevé de Ama Koudjo")
    template, data = rendered[-1]
    assert template == "releve.html.j2" and data["balance"] == 5_000
    assert [(op["label"], op["delta"]) for op in data["operations"]] == [
        ("Achat · reçu 0001", 8_000),
        ("Paiement espèces", -3_000),
    ]


async def test_stock_is_drawn_with_days_left(chat, rendered):
    got = await chat.say(
        "j'ai 20 sacs de riz",
        ("propose_stock_change", {"product": "riz", "quantity": 20, "mode": "set", "unit": "sac"}),
    )
    await chat.tap(got[0].buttons[0][0])
    sale = await chat.say("vente", SALE)  # 3 sacs
    await chat.tap(sale[0].buttons[0][0])
    stock = await chat.send(text="stock")
    assert stock[0].image and stock[0].text == "*Votre stock* · 1 produit(s) suivi(s)"
    template, data = rendered[-1]
    row = data["products"][0]
    assert template == "stock.html.j2" and (row["stock"], row["unit"], row["days"], row["low"]) == (
        17,
        "sacs",
        39,
        False,
    )


async def test_weekly_summary_has_a_bar_per_day_and_the_expenses(chat, rendered):
    sale = await chat.say("vente", SALE)
    await chat.tap(sale[0].buttons[0][0])
    spend = await chat.say("transport 3 500", ("propose_expense", {"amount": 3_500, "label": "transport"}))
    await chat.tap(spend[0].buttons[0][0])
    week = await chat.say("bilan de la semaine", ("summary", {"period": "week"}))
    assert week[0].image and week[0].text.startswith("*Bilan des 7 derniers jours*")
    template, data = rendered[-1]
    assert template == "bilan.html.j2" and len(data["days"]) == 7
    assert data["days"][-1]["current"] and data["days"][-1]["value"] == 33_000
    assert data["expense_lines"] == [{"label": "transport", "amount": 3_500}]


# --- handwritten sales register ---

REGISTER = ("sales_register", {"date": None, "lines": [
    {"product": "2 paquets d'allumette", "quantity": 2, "amount": 200},
    {"product": "boîte de tomate", "amount": 350},
    {"product": "Lait", "amount": 450, "unclear": True},
    {"product": "Riz", "amount": 1_500, "customer": "Maquis Le Palmier"},
    {"product": "Total", "amount": 2_500},  # the page total, not a sale
]})  # fmt: skip


async def test_a_register_page_becomes_cash_sales_after_one_yes(chat, db, rendered):
    chat.models.say(REGISTER)
    recap = await chat.send("image", media_id="R1")
    text = recap[0].text
    assert "J'ai lu 4 vente(s) dans votre registre" in text and "Total : *2 500 FCFA*" in text
    assert "❓ Lait : 450" in text and "Riz (Maquis Le Palmier) : 1 500" in text
    done = await chat.tap(recap[0].buttons[0][0])
    assert "4 vente(s), 2 500 FCFA" in done[0].text and "reçu de Maquis Le Palmier" in done[0].text
    async with db.session() as s:
        entries = (await s.exec(select(Entry))).all()
    assert len(entries) == 4 and all(e.debt_delta == 0 and e.source == "notebook_photo" for e in entries)
    matches = [e for e in entries if e.lines[0]["product"] == "2 paquets d'allumette"]
    assert matches[0].lines[0]["quantity"] == 2 and matches[0].lines[0]["unit_price"] == 100
    assert await contact_named(db, "Maquis Le Palmier") is not None
    assert chat.models.calls[-1]["reasoning_effort"] == "low"  # handwriting gets a little reasoning


async def test_a_register_page_is_dated_from_what_is_written(chat, db):
    from datetime import UTC, datetime, timedelta

    yesterday = (datetime.now(UTC) - timedelta(days=1)).date()
    name, args = REGISTER
    chat.models.say((name, {**args, "date": yesterday.isoformat(), "lines": args["lines"][:2]}))
    recap = await chat.send("image", media_id="R2")
    assert f"vente(s) du {yesterday:%d/%m}" in recap[0].text
    done = await chat.tap(recap[0].buttons[0][0])
    assert f"comptées le {yesterday:%d/%m}" in done[0].text
    async with db.session() as s:
        assert {e.created_at.date() for e in (await s.exec(select(Entry))).all()} == {yesterday}
    old = ("sales_register", {"date": "2020-01-02", "lines": args["lines"][:1]})
    chat.models.say(old)
    recap = await chat.send("image", media_id="R3")
    assert "vente(s) dans" in recap[0].text  # a far-off date is not trusted: counted today


# --- English for the judges (temporary) ---


async def test_english_is_chosen_first_and_replies_are_translated(db, models):
    wa = FakeWA()
    c = Chat(Services(Settings(_env_file=None), wa, FakeTranscriber(), db, Agent(models), None), models, wa)
    choice = await c.send(text="Hello")
    assert "Which language" in choice[0].text and models.calls == []
    models.say('{"texts": ["Hello! I am *Kayé* 👋 What name goes on your receipts?", "Afi"]}')
    welcome = await c.send(text="English")  # typed instead of tapped
    assert welcome[0].text.startswith("Hello! I am *Kayé*") and welcome[0].buttons == [("name:profile", "Afi")]
    assert models.calls[-1]["response_format"]["json_schema"]["name"] == "Translation"
    models.say('{"texts": ["*Afi Shop* is ready! ✅", "Try an example", "🎤 Voice note", "📸 Notebook photo"]}')
    await c.send(text="Afi Shop")
    models.say('{"texts": ["*Today\'s summary*\\nNo operation recorded."]}')
    summary = await c.send(text="summary")  # English shortcut: the only model call is the translation
    assert summary[0].text.startswith("*Today's summary*")
    async with db.session() as s:
        shop = (await s.exec(select(Shop))).one()
        assert shop.language == "en"
        from app.db.models import ModelCall

        assert len((await s.exec(select(ModelCall))).all()) == 3  # welcome, name, summary: each translation costed


async def test_a_failed_translation_sends_the_french(chat, models, db):
    async with db.session() as s:
        shop = (await s.exec(select(Shop))).one()
        shop.language = "en"
        s.add(shop)
    models.say('{"texts": []}')  # wrong count
    replies = await chat.send(text="bilan")
    assert "Bilan du jour" in replies[0].text


async def test_the_language_can_be_changed_later(chat, models):
    ask = await chat.send(text="langue")
    assert ask[0].buttons[1] == ("lang:en", "English")
    models.say('{"texts": ["Noted: I will answer in English."]}')  # translated, since English is now set
    done = await chat.tap("lang:en")
    assert done[0].text == "Noted: I will answer in English."
    chat.models.say(SALE)
    chat.models.say('{"texts": ["*Sale to Ama Koudjo*", "Yes, record", "Fix", "Cancel"]}')
    recap = await chat.send("audio", media_id="V1")
    assert FakeTranscriber.language == "English"
    assert recap[0].text == "*Sale to Ama Koudjo*" and recap[0].buttons[0][1] == "Yes, record"
    assert recap[0].buttons[0][0].startswith("ok:")  # ids are never translated
