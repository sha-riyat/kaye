# Kayé

**AI bookkeeping for West African merchants, entirely inside WhatsApp.**

In West Africa, CRMs and ERPs never reached small shops: merchants still run their business on a paper
notebook (*le cahier*) and WhatsApp Business. Kayé doesn't ask them to switch tools. The merchant talks,
photographs or types as they would to a relative; the agent records sales and debts, confirms before
writing anything, chases payments and produces receipts, all in WhatsApp and in French.

Built solo for the [Meta Global AI Developer Hackathon](https://cerebralvalley.ai/e/meta-ai-developer-hackathon)
(Indie Developer track, theme *Build for Your World*) with Meta's Muse models.

> Status: work in progress, built during the hackathon (Oct 26 – Nov 4, 2026).

## What it does

Kayé runs the whole shop from one WhatsApp conversation (in French, by voice, photo or text):

| Area | Merchant says / sends | Kayé does |
| --- | --- | --- |
| Sales & credit | « J'ai vendu 3 sacs de riz à Ama, elle me doit 8 000 » | Proposes a recap, writes after **Oui**, sends a receipt image |
| Payments | A T-Money / Flooz screenshot, or « Ama a payé 8 000 » | Matches the customer and settles the debt; a reference is never counted twice |
| Old notebook | A photo of a handwritten page | Reads each debt, flags unclear lines, imports them after one **Oui** |
| Stock | « J'ai reçu 20 sacs de riz », « il me reste 5 sacs » | Tracks levels, lowers them on sales, warns when low |
| Expenses & cash | « Transport 3 500 » | Records it; the daily summary shows what should be in the till |
| Suppliers | « Je dois 180 000 à Koffi, vendredi » | Records the debt, reminds the day before it is due |
| Team | « Ajoute mon vendeur +228… » | The seller can record sales; only the owner sees totals and debts |
| Follow-up | « Qui me doit ? », « bilan », « annule » | Answers from the ledger, prepares a polite reminder with a `wa.me` link |

The rule behind it: **the model proposes, the merchant validates, the code writes.** The model only picks one
tool and fills its arguments. The code resolves names, recomputes every amount, writes the confirmation
text and applies the write only when the merchant taps *Oui*. Nothing is ever deleted: a correction
inserts a reversing entry. Reads (balances, debtors, summaries, stock) are answered by code, with no
second model call.

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

## Built during the hackathon

All code in this repository was written during the event; see the commit history.

## License

MIT
