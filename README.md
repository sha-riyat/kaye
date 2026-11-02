<p align="right"><b>English</b> · <a href="README.fr.md">Français</a></p>

<p align="center">
  <img src="docs/img/banner-en.png" alt="Kayé: Parle. Kayé note. (Speak. Kayé takes note.) The shop assistant of West African merchants, entirely inside WhatsApp." width="100%">
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

## The problem

In West Africa, CRMs and ERPs never reached small shops. A grocery in Lomé, a seller who delivers
orders bought on Instagram, a market stall: they run their business on a **paper notebook**
(*le cahier*) and on **WhatsApp**. Credit is common, so knowing who owes what is survival, and it
lives on paper that gets lost, wet or misread.

**Kayé doesn't ask them to switch tools.** The merchant talks, photographs or types in French, as
they would to a relative. Kayé keeps the books, confirms before writing anything, chases payments
and sends receipts in the shop's name, all inside the WhatsApp they already use every day.

> **The rule behind it: the model proposes, the merchant validates, the code writes.**
> The model only picks a tool and fills its arguments. The code resolves names, recomputes every
> amount, writes the confirmation text, and applies the write only when the merchant taps
> **« Oui »** (*yes*). Nothing is ever deleted: a correction inserts a reversing entry.

## How it works

<p align="center"><img src="docs/img/architecture-en.png" alt="Architecture: merchant, WhatsApp Cloud API, webhook on Modal, understanding with Meta models, decision, then either an immediate answer or a proposal confirmed by Oui, written to the ledger, with documents sent back in WhatsApp. Storage: Supabase Postgres, Cloudflare R2, hourly Modal cron." width="100%"></p>

1. **The merchant** sends a voice note, a photo or a text to the shop's WhatsApp number, or taps a button.
2. **WhatsApp Cloud API** forwards it to Kayé's webhook.
3. **The webhook** (FastAPI on Modal) checks Meta's signature, drops duplicate deliveries, answers
   Meta in under a second and hands the message to a background job.
4. **Understand:** a voice note is transcribed by *Muse Voice Transcribe*; a photo is cleaned up
   (upright, grey, contrast) and read by *Muse Spark*'s vision; a text goes straight to *Muse Spark*.
5. **Decide:** *Muse Spark* picks one or several typed tools (sale, payment, expense, stock,
   question…) and fills their arguments. From here on, **only code runs**: it finds the customer,
   recomputes every total, and writes the reply itself.
6. **A question** (« bilan » *summary*, « stock », « qui me doit ? » *who owes me?*) is answered at
   once, often as a ticket image. **An operation** becomes one recap with three buttons:
   **Oui · Corriger · Annuler** (*Yes · Fix · Cancel*).
7. **The merchant taps « Oui ».** Nothing was written before that tap.
8. **The ledger** receives the entries. Balances are never stored, they are summed from entries,
   so every figure traces back to the message that created it.
9. **Documents** (receipt, quittance, summary…) are drawn from HTML templates into PNG images with
   headless Chromium, stored in R2 and sent back in WhatsApp, ready to forward to the customer.

Every hour a **Modal cron** sends each shop its evening summary at the shop's own hour, and
reminds the merchant of supplier payments due the next day.

## What it does

<p align="center"><img src="docs/img/features-en.png" alt="Sales and credit, voice notes, notebook photo, mobile money, stock, expenses, suppliers, receipts, summaries, reminders" width="100%"></p>

Merchants speak French; the English translation is in italics.

| The merchant says or sends | Kayé does |
| --- | --- |
| « J'ai vendu 3 sacs de riz à Ama, elle me doit 8 000 »<br>*I sold 3 bags of rice to Ama, she owes me 8,000* | Proposes one recap, writes it after **Oui**, then sends a receipt image to forward to Ama |
| A photo of the day's **sales register** (products and prices) | Reads every line, marks unclear ones ❓, records them all as cash sales after one **Oui** |
| A photo of the **credit notebook** (names and what each one owes) | Imports each debt |
| A T-Money or Flooz screenshot, or « Ama a payé 8 000 » *Ama paid 8,000* | Settles the right debt (a mobile money reference is never counted twice) and sends a **quittance** (*proof of full payment*) when the debt is cleared |
| « J'ai reçu 20 sacs de riz » *I received 20 bags of rice*, or a photo of the shelf | Tracks stock; *SAM 3.1* counts the bags on the photo |
| « Transport 3 500 » · « Je dois 180 000 à Koffi, vendredi » *I owe Koffi 180,000, due Friday* | Records the expense and the supplier debt, reminds the merchant the day before it falls due |
| « bilan » *summary* · « stock » · « relevé d'Ama » *Ama's statement* · « qui me doit ? » *who owes me?* | Answers with a branded ticket image: the day's or week's figures, stock with days left, a customer's account, debtors with a ready-to-send reminder |
| « Ajoute mon vendeur +228… » *Add my seller +228…* | The seller can record sales; only the owner sees totals and debts |
| « Crée mon logo » *Make me a logo* | *Muse Image* draws three logos; the chosen one goes on every document |

A long voice note with several operations (a sale, a delivery, an expense) gives **one recap with
one set of buttons**. A missing price or customer is asked at the bottom of the same recap, and Kayé
remembers the last turns, so « et Kofi aussi » (*and Kofi too*) or « non, 12 000 » (*no, 12,000*)
are understood in context.

### Documents, in the shop's name

Each document is a paper ticket in the Kayé style, sent as an image the merchant forwards to the
customer: the shop's name and logo on top, a discreet Kayé seal at the bottom. Below: a receipt, a
weekly summary with a bar per day, the stock with how many days it lasts, a quittance stamped
« SOLDÉ » (*paid in full*).

<p align="center"><img src="docs/img/documents.png" alt="A receipt, a weekly summary, a stock ticket and a quittance, as Kayé sends them" width="100%"></p>

### Two kinds of notebooks

Most shops write the day's sales as **products and prices, with no customer names**; they need
their totals, not receipts. Shops that sell online or take orders write a **customer or company
name** on the line, because they owe that customer a receipt. Kayé reads both from a phone photo,
uses the date written on the page, and leaves out crossed-out and total lines.

On a real handwritten register page photographed with a phone, every amount and the date were read
right; a few product words came back marked ❓, and the merchant fixes them with **Corriger**
(*Fix*) in their own words.

## Getting started

### For a merchant: 2 minutes, nothing to install

1. Write **« Bonjour »** (*hello*) to [+228 71 67 45 79](https://wa.me/22871674579?text=Bonjour).
2. Answer with the name of your shop, for example « Chez Afi ».
3. Send your first operation: a voice note « J'ai vendu 2 sacs de riz à Ama à 12 000 le sac, elle a
   payé 20 000 » (*I sold 2 bags of rice to Ama at 12,000 a bag, she paid 20,000*), or a photo of
   today's page of your notebook.
4. Check the recap and tap **Oui**. The receipt arrives, ready to forward.
5. Ask « bilan » in the evening, « stock » before ordering, « qui me doit ? » to chase payments.

Photos read best flat, well lit, with the whole page in the frame. To use your own logo, send it as
a photo with the caption « logo ». To erase everything: « supprimer mes données » (*delete my data*).

### For a developer

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), a [Modal](https://modal.com) account,
a Meta app with the WhatsApp use case, a Supabase Postgres and a Cloudflare R2 bucket. Locally,
documents need Chromium, Chrome or Edge, and voice notes need ffmpeg. Linux, macOS and Windows work.

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
`https://<your-modal-url>/webhook` and the verify token to `WHATSAPP_VERIFY_TOKEN`, and subscribe
to `messages`. `uv run python -m scripts.whatsapp_setup <url>` does it and checks the account.

**Try it without WhatsApp:** replay a conversation against the real agent and models.

```bash
uv run python -m scripts.replay tests/fixtures/conversations/demo.txt --db postgresql://localhost/kaye_scratch
```

## Meta models used

| Model | Used for | Measured cost |
| --- | --- | --- |
| **Muse Spark 1.3** | Understands each message and picks typed tools (`reasoning_effort=minimal`); reads handwritten pages and mobile money screenshots (`low`, on a cleaned-up photo) | ≈ $0.0045 per message · $0.005–0.01 per page |
| **Muse Voice Transcribe 1.0** | French voice notes, biased toward market words (tas, bol, sac, T-Money, Flooz…) | $0.18 per audio hour |
| **SAM 3.1** | Counts items on a stock photo | $0.0025 per photo |
| **Muse Image 1.0** | Draws shop logos | $0.01 per logo |

Every call is logged with its cost; `uv run python -m scripts.costs` prints the cost per active
merchant-day. A merchant sending 15 messages a day, half of them short voice notes, costs about
**$2.20 a month** (≈ 1,300 FCFA). Shortcuts and buttons (« bilan », « stock », « qui me doit ? »)
use no model at all. `scripts/handwriting_eval.py` compares ways of reading handwriting on any photos.

**Key files:** `app/agent/` (prompts, tools, the agent loop) · `app/db/ledger.py` (the only place
entries are created) · `app/documents/templates/` (the ticket family) · `app/receipts.py`
(HTML → PNG) · `app/images.py` (photo clean-up) · `app/jobs.py` (hourly jobs).

## Brand

<p align="center"><img src="docs/img/logo.png" alt="Kayé logo: the cowrie and the word kayé" width="100%"></p>

The symbol is a **money cowrie**, the historic currency of West Africa. Its aperture is drawn as a
zigzag of teeth that also reads as a voice wave: Kayé listens, then writes it down. The tagline says
it: « Parle. Kayé note. » (*Speak. Kayé takes note.*)

<p align="center"><img src="docs/img/palette-en.png" alt="Palette: Nuit de Lomé #14111B, Cauri #F5E9D6, Solaire #FF7A1F, Latérite #B84A1E, Lagune #17705F" width="100%"></p>

Each colour keeps one meaning everywhere: **Latérite** (*red earth*) is what is still due,
**Lagune** (*lagoon*) what is paid, **Solaire** (*sun*) what calls for action. Titles and amounts are
set in **Bricolage Grotesque**, text in **Inter**; amounts are always written `148 500 FCFA`.

| Asset | File |
| --- | --- |
| Profile picture (WhatsApp, Facebook, Instagram), 2048 px | [`profile-solaire-2048.png`](assets/brand/profile-solaire-2048.png) · [`profile-night-2048.png`](assets/brand/profile-night-2048.png) |
| Logo, symbol, wordmark, icons (SVG) | [`assets/brand/`](assets/brand) |
| Documents, live on a local design canvas | `uv run uvicorn design.server:app --reload --port 8765` |

`uv run python -m scripts.brand_export` regenerates the lockups, profile pictures and every image of this README.

## Privacy and safety

- Every WhatsApp number is its own user, attached to one shop; every query is scoped by shop.
- Webhooks are authenticated (`X-Hub-Signature-256`) and deduplicated by message id.
- Row Level Security is on for every table: the public Supabase API sees nothing.
- Voice notes, photos, receipts and logos live in a private R2 bucket.
- Merchant data is never used to train models (no contributor-tier models are used).
- Kayé never messages a merchant's customer: it prepares the text, the merchant sends it.
- « supprimer mes données » (*delete my data*) erases a shop's records, users and files after a yes.
- A per-shop daily quota, a global daily model budget and a blocklist protect the public number.

## Built during the hackathon

All code in this repository was written during the event (Oct 26 – Nov 4, 2026); see the commit
history. The shelf photo in `tests/fixtures/images/shelf_rice.jpg` is AI-generated (Muse Image) for tests.

## License

MIT
