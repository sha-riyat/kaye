<p align="center">
  <img src="docs/img/banner.png" alt="Kayé: Parle. Kayé note. The shop assistant of West African merchants, entirely in WhatsApp." width="100%">
</p>

<p align="center">
  <b>An AI shop assistant for West African merchants, entirely inside WhatsApp.</b><br>
  Built solo for the <a href="https://cerebralvalley.ai/e/meta-ai-developer-hackathon">Meta Global AI Developer Hackathon</a>
  · Indie Developer track · <i>Build for Your World</i>
</p>

<p align="center">
  <a href="https://wa.me/22871674579?text=Bonjour"><b>Try it on WhatsApp: +228 71 67 45 79</b></a>
  &nbsp;·&nbsp; demo mode, please use fictitious data
</p>

---

In West Africa, CRMs and ERPs never reached small shops: merchants run their business on a paper
notebook (*le cahier*) and WhatsApp. Kayé doesn't ask them to switch tools. The merchant talks,
photographs or types as they would to a relative; Kayé keeps the books, confirms before writing
anything, chases payments and sends receipts, all in WhatsApp and in French.

> **The rule behind it: the model proposes, the merchant validates, the code writes.**
> The model only picks a tool and fills its arguments. The code resolves names, recomputes every
> amount, writes the confirmation text and applies the write only when the merchant taps *Oui*.
> Nothing is ever deleted: a correction inserts a reversing entry.

## What it does

<p align="center"><img src="docs/img/features.png" alt="Sales and credit, voice notes, notebook photo, mobile money, stock, expenses, suppliers, receipts, summaries, reminders" width="100%"></p>

| Merchant says or sends | Kayé does |
| --- | --- |
| « J'ai vendu 3 sacs de riz à Ama, elle me doit 8 000 » | One recap, written after **Oui**, then a receipt image to forward |
| A photo of the day's **sales register** (products and prices) | Reads every line, marks unclear ones ❓, records them all as cash sales after one **Oui** |
| A photo of the **credit notebook** (names and what they owe) | Imports each debt |
| A T-Money / Flooz screenshot, or « Ama a payé 8 000 » | Settles the right debt (a reference is never counted twice) and sends a **quittance** when it is cleared |
| « J'ai reçu 20 sacs de riz », or a photo of the shelf | Tracks stock; SAM 3.1 counts the sacks on the photo |
| « Transport 3 500 » · « Je dois 180 000 à Koffi, vendredi » | Records expenses and supplier debts, reminds the day before they fall due |
| « bilan » · « stock » · « relevé d'Ama » · « qui me doit ? » | Answers with a branded ticket image: summary, stock with days left, account statement, debtors with a ready reminder |
| « Ajoute mon vendeur +228… » | The seller can record sales; only the owner sees totals and debts |
| « Crée mon logo » | Muse Image draws three logos; the chosen one goes on every document |

A long voice note with several operations gives **one recap with one Oui / Corriger / Annuler**.
A missing price or customer is asked at the bottom of the same recap, and Kayé remembers the last
turns, so « et Kofi aussi » or « non, 12 000 » are read in context.

### Documents, in the shop's name

Every document is a ticket in the Kayé style, sent as an image the merchant forwards to the customer.
The shop's name and logo are on top; Kayé signs discreetly at the bottom.

<p align="center"><img src="docs/img/documents.png" alt="A receipt, a weekly summary with a bar per day, a stock ticket with days left, a quittance stamped SOLDÉ" width="100%"></p>

### Two kinds of notebooks

Most shops write the day's sales as **products and prices, with no customer names**. Shops that
sell online or take orders write a **name** on the line, because they owe that customer a receipt.
Kayé reads both from a phone photo, with the page's date when it is written, and leaves out
crossed-out and total lines. Measured on a real register page: every amount and the date read
right; a few product words come back marked ❓ and are fixed with *Corriger*.

## Onboarding

### For a merchant (2 minutes, nothing to install)

1. Write **« Bonjour »** to [+228 71 67 45 79](https://wa.me/22871674579?text=Bonjour).
2. Answer with the name of your shop: « Chez Afi ».
3. Say or send your first operation: a voice note « J'ai vendu 2 sacs de riz à Ama à 12 000 le sac,
   elle a payé 20 000 », or a photo of today's page of your notebook.
4. Check the recap and tap **Oui**. The receipt arrives, ready to forward.
5. Ask **« bilan »** in the evening, **« stock »** before ordering, **« qui me doit ? »** to chase payments.

Tips for photos: the page flat and well lit, the whole page in the frame. To set your own logo, send
it as a photo with the caption « logo ». To erase everything: « supprimer mes données ».

### For a developer

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), a [Modal](https://modal.com) account,
a Meta app with the WhatsApp use case, a Supabase Postgres and a Cloudflare R2 bucket. Locally,
documents need Chromium, Chrome or Edge, and voice notes need ffmpeg (Linux, macOS and Windows).

```bash
uv sync
cp .env.example .env              # fill in the values
uv run pytest                     # webhook and documents; flow tests need TEST_DATABASE_URL
```

Flow and ledger tests run against a real Postgres:

```bash
docker run -d --name kaye-pg -e POSTGRES_PASSWORD=kaye -p 127.0.0.1:54329:5432 postgres:17
docker exec kaye-pg psql -U postgres -c "create database kaye_test"
TEST_DATABASE_URL=postgresql://postgres:kaye@127.0.0.1:54329/kaye_test uv run pytest
```

On Windows PowerShell, set the variable first: `$env:TEST_DATABASE_URL = "postgresql://…"`.

Deploy:

```bash
uv run alembic upgrade head                                         # DATABASE_URL from .env
uv run modal setup                                                  # once
uv run modal secret create kaye-secrets --from-dotenv .env --force
uv run modal deploy modal_app.py                                    # stable URL + hourly jobs
```

Then in the Meta dashboard (WhatsApp → Configuration → Webhook), set the callback URL to
`https://<your-modal-url>/webhook`, the verify token to `WHATSAPP_VERIFY_TOKEN`, and subscribe to
`messages` (`uv run python -m scripts.whatsapp_setup <url>` does it and checks the account).

**Try it without WhatsApp:** replay a conversation against the real agent and models.

```bash
uv run python -m scripts.replay tests/fixtures/conversations/demo.txt --db postgresql://localhost/kaye_scratch
```

## Meta models used

| Model | Used for | Measured cost |
| --- | --- | --- |
| Muse Spark 1.3 | Understands each message and picks typed tools (`reasoning_effort=minimal`); reads handwritten pages and mobile money screenshots (`low`, on a cleaned-up photo) | ≈ $0.0045 per message · $0.005–0.01 per page |
| Muse Voice Transcribe 1.0 | French voice notes, biased to market words (tas, bol, sac, T-Money, Flooz…) | $0.18 per audio hour |
| SAM 3.1 | Counts items on a stock photo | $0.0025 per photo |
| Muse Image 1.0 | Draws shop logos | $0.01 per logo |

Every call is logged with its cost; `uv run python -m scripts.costs` prints the cost per active
merchant-day. A merchant sending 15 messages a day (half of them short voice notes) costs about
**$2.20 a month** (≈ 1 300 FCFA). Shortcuts and buttons (« bilan », « stock », « qui me doit ? »)
use no model at all. `scripts/handwriting_eval.py` compares ways of reading handwriting on any photos.

## Architecture

```
WhatsApp Cloud API ──POST──▶ FastAPI webhook on Modal (signature check, wamid dedup, 200 at once)
                               └─ spawns a background job
                                    router ─┬─ voice  ─▶ Muse Voice Transcribe ─┐
                                            ├─ photo  ─▶ cleaned up ─▶ Muse Spark (vision)
                                            └─ text / button tap ───────────────┤
                                                                                ▼
                                   Muse Spark picks tools ─▶ actions.py (code):
                                     read tools   → answer, often as a ticket image
                                     write tools  → pending action + Oui / Corriger / Annuler
                                     "Oui"        → ledger entries → receipt / quittance PNG → R2 → WhatsApp
                                   shelf photo → SAM 3.1 counts · « logo » → Muse Image
Supabase Postgres (ledger: balances are summed, never stored) · Cloudflare R2 (media, receipts)
Modal cron, hourly: each shop's evening summary at its hour, supplier reminders the day before
```

Key files: `app/agent/` (prompts, tools, loop), `app/db/ledger.py` (the only place entries are
created), `app/documents/templates/` (the ticket family), `app/receipts.py` (HTML → PNG with
headless Chromium), `app/images.py` (photo clean-up), `app/jobs.py`.

## Brand

<p align="center"><img src="docs/img/logo.png" alt="Kayé logo: the cowrie and the word kayé" width="100%"></p>

The symbol is a **money cowrie**, the historic currency of West Africa; its aperture is drawn as a
zigzag of teeth that also reads as a voice wave: Kayé listens, then writes it down.

<p align="center"><img src="docs/img/palette.png" alt="Palette: Nuit de Lomé #14111B, Cauri #F5E9D6, Solaire #FF7A1F, Latérite #B84A1E, Lagune #17705F" width="100%"></p>

Each colour keeps one meaning everywhere: **Latérite** is what is still due, **Lagune** what is
paid, **Solaire** what calls for action. Titles and amounts are set in **Bricolage Grotesque**, text
in **Inter**; amounts are always written `148 500 FCFA`.

| Asset | File |
| --- | --- |
| Profile picture (WhatsApp, Facebook, Instagram), 2048 px | [`profile-solaire-2048.png`](assets/brand/profile-solaire-2048.png) · [`profile-night-2048.png`](assets/brand/profile-night-2048.png) |
| Logo, symbol, wordmark (SVG) | [`assets/brand/`](assets/brand) |
| Documents, live on a local canvas | `uv run uvicorn design.server:app --reload --port 8765` |

`uv run python -m scripts.brand_export` regenerates the lockups, profile pictures and the images of this README.

## Privacy and safety

- Every WhatsApp number is its own user, attached to one shop; every query is scoped by shop.
- Webhooks are authenticated (`X-Hub-Signature-256`) and deduplicated by message id.
- Row Level Security is on for every table: the public Supabase API sees nothing.
- Media (voice notes, photos, receipts, logos) live in a private R2 bucket.
- Merchant data is never used to train models (no contributor-tier models are used).
- Kayé never messages a merchant's customer: it prepares the text, the merchant sends it.
- « supprimer mes données » erases a shop's records, users and files after a yes.
- Per-shop daily quota, a global daily model budget and a blocklist protect the public number.

## Built during the hackathon

All code in this repository was written during the event (Oct 26 – Nov 4, 2026); see the commit
history. The shelf photo in `tests/fixtures/images/shelf_rice.jpg` is AI-generated (Muse Image) for tests.

## License

MIT
