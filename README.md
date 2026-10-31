# Kayé

**An AI shop assistant for West African merchants, entirely inside WhatsApp.**

In West Africa, CRMs and ERPs never reached small shops: merchants still run their business on a paper
notebook (*le cahier*) and WhatsApp Business. Kayé doesn't ask them to switch tools. The merchant talks,
photographs or types as they would to a relative; Kayé keeps the books (sales, credit, stock, expenses,
suppliers), confirms before writing anything, chases payments and sends receipts, all in WhatsApp and
in French.

**Try it:** write « Bonjour » on WhatsApp to **+228 71 67 45 79**
([wa.me/22871674579](https://wa.me/22871674579?text=Bonjour)). Demo mode: please use fictitious data.

Built solo for the [Meta Global AI Developer Hackathon](https://cerebralvalley.ai/e/meta-ai-developer-hackathon)
(Indie Developer track, theme *Build for Your World*) with Meta's Muse models.

> Built during the hackathon (Oct 26 – Nov 4, 2026). Deployed on a real WhatsApp Business number.

## What it does

Kayé runs the whole shop from one WhatsApp conversation (in French, by voice, photo or text):

| Area | Merchant says / sends | Kayé does |
| --- | --- | --- |
| Sales & credit | « J'ai vendu 3 sacs de riz à Ama, elle me doit 8 000 » | Proposes a recap, writes after **Oui**, sends a receipt image |
| Payments | A T-Money / Flooz screenshot, or « Ama a payé 8 000 » | Matches the customer and settles the debt; a reference is never counted twice |
| Old notebook | A photo of a handwritten page | Reads each debt, flags unclear lines, imports them after one **Oui** |
| Stock | « J'ai reçu 20 sacs de riz », or a photo of the shelf | Tracks levels, lowers them on sales, warns when low; SAM 3.1 counts the sacks on a photo |
| Expenses & cash | « Transport 3 500 » | Records it; the daily summary shows what should be in the till |
| Suppliers | « Je dois 180 000 à Koffi, vendredi » | Records the debt, reminds the day before it is due |
| Team | « Ajoute mon vendeur +228… » | The seller can record sales; only the owner sees totals and debts |
| Follow-up | « Qui me doit ? », « bilan », « annule », « reçu » | Answers from the ledger, prepares a polite reminder with a `wa.me` link, resends a receipt |
| Branding | « Crée mon logo » | Muse Image draws three logos; the chosen one goes on every receipt |

A long voice note with several operations (« j'ai vendu… j'ai reçu… le transport m'a coûté… ») gives
**one recap with one Oui / Corriger / Annuler**. If something is missing (a price, who bought what,
how much is owed to the supplier), the question sits at the bottom of the same recap and the merchant
answers in their own words. Kayé remembers the last turns of the conversation, so « et Kofi aussi »
or « non, 12 000 » are read in context.

The rule behind it: **the model proposes, the merchant validates, the code writes.** The model only picks one
tool and fills its arguments. The code resolves names, recomputes every amount, writes the confirmation
text and applies the write only when the merchant taps *Oui*. Nothing is ever deleted: a correction
inserts a reversing entry. Reads (balances, debtors, summaries, stock) are answered by code, with no
second model call.

## Meta models used

| Model | Used for | Measured cost |
| --- | --- | --- |
| Muse Spark 1.3 (`reasoning_effort=minimal`) | Understands each message and picks one or several typed tools; reads notebook pages and mobile money screenshots | ≈ $0.0045 per message (≈ 2,850 input tokens) |
| Muse Voice Transcribe 1.0 | French voice notes, with a market vocabulary bias (tas, bol, sac, T-Money, Flooz…) | $0.18 per audio hour (≈ $0.003 per minute) |
| SAM 3.1 | Counts items on a stock photo (« sack », « carton ») | $0.0025 per photo |
| Muse Image 1.0 | Draws shop logos | $0.01 per logo |

Every call is logged with its cost in `model_call`; `uv run python -m scripts.costs` prints the cost
per active merchant-day. For a merchant sending 15 messages a day (half of them voice notes of
15 s), the model cost is about **$2.20 a month** (≈ 1,300 FCFA). Buttons and shortcuts (« bilan »,
« qui me doit ? ») use no model at all.

## Architecture

```
WhatsApp Cloud API ──POST──▶ FastAPI webhook on Modal (signature check, wamid dedup, 200 at once)
                               └─ spawns a background job
                                    router ─┬─ voice  ─▶ Muse Voice Transcribe ─┐
                                            ├─ photo  ─▶ Muse Spark (vision) ───┤
                                            └─ text / button tap ───────────────┤
                                                                                ▼
                                   Muse Spark picks ONE tool ─▶ actions.py (code):
                                     read tools   → answer directly
                                     write tools  → pending action + Oui / Corriger / Annuler
                                     "Oui"        → ledger entry → receipt PNG → R2 → WhatsApp
                                   photo of a shelf → SAM 3.1 counts · « logo » → Muse Image
Supabase Postgres (ledger, balances are summed, never stored) · Cloudflare R2 (media, receipts)
Modal cron, hourly: evening summary at each shop's hour, supplier due-date reminders
```

Key files: `app/agent/` (prompts, tools, loop), `app/db/ledger.py` (the only place entries are created),
`app/receipts.py` (HTML templates → PNG with headless Chromium), `app/jobs.py`, `scripts/replay.py`.

## Try it without WhatsApp

```bash
createdb kaye_scratch   # any scratch Postgres: the script wipes it
uv run python -m scripts.replay tests/fixtures/conversations/demo.txt --db postgresql://localhost/kaye_scratch
```

It replays a conversation against the real agent and models and prints every reply with its buttons.

## Setup

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), a [Modal](https://modal.com) account,
a Meta app with the WhatsApp use case.

```bash
uv sync
cp .env.example .env            # fill in the values
uv run pytest                   # fake payloads, no network (flow tests need TEST_DATABASE_URL)
uv run modal setup              # once
uv run modal secret create kaye-secrets --from-dotenv .env --force
uv run modal serve modal_app.py # public HTTPS URL with hot reload
uv run modal deploy modal_app.py # stable URL + hourly jobs
```

Database (Supabase Postgres, transaction pooler on port 6543):

```bash
uv run alembic upgrade head     # uses DATABASE_URL from .env

# Ledger tests run against a real Postgres:
docker run -d --name kaye-pg -e POSTGRES_PASSWORD=kaye -p 127.0.0.1:54329:5432 postgres:17
docker exec kaye-pg psql -U postgres -c "create database kaye_test"
TEST_DATABASE_URL=postgresql://postgres:kaye@127.0.0.1:54329/kaye_test uv run pytest
```

Balances are never stored: they are summed from ledger entries, and a correction inserts a
reversing entry instead of deleting anything, so every figure traces back to the message that
created it.

Then in the Meta dashboard (WhatsApp → Configuration → Webhook), set the callback URL to
`https://<your-modal-url>/webhook`, the verify token to `WHATSAPP_VERIFY_TOKEN`, and subscribe to the
`messages` field.

## Design canvas for documents

Receipts, invoices and reminders Kayé sends are HTML templates (`app/documents/templates`). A local
canvas shows every template live with fictitious data, so variants can be compared side by side:

```bash
uv run uvicorn design.server:app --reload --reload-dir app/documents --reload-dir design --port 8765
# open http://localhost:8765
```

Items live in `design/registry.py` (stable id, readable name, template, fixture, size). To try
another version, add an entry; to iterate, edit the template: open previews refresh by themselves.
Drag the background to pan, Ctrl/⌘ + wheel or pinch to zoom, drag the ⋮⋮ handle to move an item,
click a name to copy it.

## Privacy and safety

- Every WhatsApp number is its own user, attached to one shop; every query is scoped by shop.
- Webhooks are authenticated (`X-Hub-Signature-256`) and deduplicated by message id.
- Row Level Security is on for every table: the public Supabase API sees nothing.
- Media (voice notes, photos, receipts, logos) live in a private R2 bucket.
- Merchant data is never used to train models (no contributor-tier models are used).
- Kayé never messages a merchant's customer: it prepares the text, the merchant sends it.
- Per-shop daily quota and a global daily model budget protect the public number.

## Built during the hackathon

All code in this repository was written during the event; see the commit history.
The shelf photo in `tests/fixtures/images/shelf_rice.jpg` is AI-generated (Muse Image) for tests.

## License

MIT
