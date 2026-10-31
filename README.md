# Kayé

**AI bookkeeping for West African merchants, entirely inside WhatsApp.**

In West Africa, CRMs and ERPs never reached small shops: merchants still run their business on a paper
notebook (*le cahier*) and WhatsApp Business. Kayé doesn't ask them to switch tools. The merchant talks,
photographs or types as they would to a relative; the agent records sales and debts, confirms before
writing anything, chases payments and produces receipts, all in WhatsApp and in French.

Built solo for the [Meta Global AI Developer Hackathon](https://cerebralvalley.ai/e/meta-ai-developer-hackathon)
(Indie Developer track, theme *Build for Your World*) with Meta's Muse models.

> Status: work in progress, built during the hackathon (Oct 26 – Nov 4, 2026).

## Architecture (current)

```
WhatsApp Cloud API ──POST──▶ FastAPI webhook on Modal
                               ├─ verifies X-Hub-Signature-256
                               ├─ deduplicates by message id (wamid)
                               ├─ returns 200 immediately
                               └─ spawns a background Modal job ──▶ router ──▶ reply via Cloud API
```

## Setup

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), a [Modal](https://modal.com) account,
a Meta app with the WhatsApp use case.

```bash
uv sync
cp .env.example .env            # fill in the values
uv run pytest                   # tests use fake payloads, no network
uv run modal setup              # once
uv run modal secret create kaye-secrets --from-dotenv .env --force
uv run modal serve modal_app.py # public HTTPS URL with hot reload
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
