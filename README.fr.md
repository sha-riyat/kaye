<p align="right"><a href="README.md">English</a> · <b>Français</b></p>

<p align="center">
  <img src="docs/img/banner-fr.png" alt="Kayé : Parle. Kayé note. L'assistant de boutique des commerçants d'Afrique de l'Ouest, entièrement dans WhatsApp." width="100%">
</p>

<p align="center">
  <b>Un assistant de boutique pour les commerçants d'Afrique de l'Ouest, entièrement dans WhatsApp.</b><br>
  Construit en solo pour le <a href="https://cerebralvalley.ai/e/meta-ai-developer-hackathon">Meta Global AI Developer Hackathon</a>
  · catégorie Indie Developer · <i>Build for Your World</i>
</p>

<p align="center">
  <a href="https://wa.me/22871674579?text=Bonjour"><b>Essayer sur WhatsApp : +228 71 67 45 79</b></a>
  &nbsp;·&nbsp; mode démo, utilisez des données fictives
</p>

---

## Le problème

En Afrique de l'Ouest, les logiciels de gestion ne sont jamais arrivés jusqu'aux petites boutiques.
Une alimentation à Lomé, une vendeuse qui livre des commandes passées sur Instagram, un étal au
marché : tout tient sur un **cahier** et sur **WhatsApp**. Le crédit est courant, donc savoir qui doit
quoi est vital, et cette information vit sur du papier qui se perd, se mouille ou se lit mal.

**Kayé ne demande pas de changer d'outil.** Le commerçant parle, photographie ou écrit, comme il le
ferait à un proche. Kayé tient les comptes, confirme avant d'écrire quoi que ce soit, relance les
paiements et envoie les reçus au nom de la boutique, dans le WhatsApp qu'il utilise déjà tous les jours.

> **La règle : le modèle propose, le commerçant valide, le code écrit.**
> Le modèle ne fait que choisir un outil et remplir ses arguments. Le code retrouve les noms,
> recalcule chaque montant, rédige le message de confirmation, et n'écrit que lorsque le commerçant
> appuie sur **« Oui »**. Rien n'est jamais effacé : une correction ajoute une écriture inverse.

## Comment ça marche

<p align="center"><img src="docs/img/architecture-fr.png" alt="Architecture : commerçant, WhatsApp Cloud API, webhook sur Modal, compréhension par les modèles Meta, décision, puis réponse immédiate ou proposition confirmée par Oui, écrite dans le cahier, documents renvoyés dans WhatsApp. Stockage : Supabase Postgres, Cloudflare R2, tâches horaires Modal." width="100%"></p>

1. **Le commerçant** envoie un vocal, une photo ou un texte au numéro WhatsApp, ou appuie sur un bouton.
2. **WhatsApp Cloud API** le transmet au webhook de Kayé.
3. **Le webhook** (FastAPI sur Modal) vérifie la signature de Meta, ignore les doublons, répond à
   Meta en moins d'une seconde et confie le message à une tâche en arrière-plan.
4. **Comprendre :** un vocal est transcrit par *Muse Voice Transcribe* ; une photo est nettoyée
   (redressée, en gris, contrastée) puis lue par la vision de *Muse Spark* ; un texte va directement
   à *Muse Spark*.
5. **Décider :** *Muse Spark* choisit un ou plusieurs outils typés (vente, paiement, dépense, stock,
   question…) et remplit leurs arguments. À partir de là, **seul le code travaille** : il retrouve
   le client, recalcule chaque total et rédige lui-même la réponse.
6. **Une question** (« bilan », « stock », « qui me doit ? ») reçoit tout de suite sa réponse, souvent
   sous forme de ticket en image. **Une opération** devient un seul récapitulatif avec trois boutons :
   **Oui · Corriger · Annuler**.
7. **Le commerçant appuie sur « Oui ».** Rien n'a été écrit avant.
8. **Le cahier** reçoit les écritures. Les soldes ne sont jamais stockés : ils sont recalculés à
   partir des écritures, donc chaque chiffre remonte au message qui l'a créé.
9. **Les documents** (reçu, quittance, bilan…) sont dessinés à partir de modèles HTML, convertis en
   image par Chromium, rangés dans R2 et renvoyés dans WhatsApp, prêts à transférer au client.

Chaque heure, une **tâche Modal** envoie à chaque boutique son bilan du soir à l'heure choisie, et
rappelle au commerçant les paiements fournisseurs du lendemain.

## Ce que fait Kayé

<p align="center"><img src="docs/img/features-fr.png" alt="Ventes et crédits, vocaux, photo du cahier, mobile money, stock, dépenses, fournisseurs, reçus, bilans, relances" width="100%"></p>

| Le commerçant dit ou envoie | Kayé |
| --- | --- |
| « J'ai vendu 3 sacs de riz à Ama, elle me doit 8 000 » | Propose un récapitulatif, l'écrit après **Oui**, puis envoie le reçu en image à transférer à Ama |
| La photo du **registre des ventes** du jour (produits et prix) | Lit chaque ligne, marque ❓ celles qui sont peu lisibles, enregistre tout en ventes au comptant après un seul **Oui** |
| La photo du **cahier de crédits** (noms et ce que chacun doit) | Reprend chaque dette |
| Une capture T-Money ou Flooz, ou « Ama a payé 8 000 » | Solde la bonne dette (une référence mobile money n'est jamais comptée deux fois) et envoie une **quittance** quand la dette est soldée |
| « J'ai reçu 20 sacs de riz », ou une photo de l'étagère | Suit le stock ; *SAM 3.1* compte les sacs sur la photo |
| « Transport 3 500 » · « Je dois 180 000 à Koffi, vendredi » | Note la dépense et la dette fournisseur, et la rappelle la veille de l'échéance |
| « bilan » · « stock » · « relevé d'Ama » · « qui me doit ? » | Répond par un ticket en image : les chiffres du jour ou de la semaine, le stock avec les jours restants, le compte d'un client, les dettes avec un rappel prêt à envoyer |
| « Ajoute mon vendeur +228… » | Le vendeur peut noter des ventes ; seul le patron voit les totaux et les dettes |
| « Crée mon logo » | *Muse Image* dessine trois logos ; celui choisi va sur tous les documents |

Un long vocal avec plusieurs opérations (une vente, une livraison, une dépense) donne **un seul
récapitulatif avec un seul jeu de boutons**. Un prix ou un client manquant est demandé en bas du même
récapitulatif, et Kayé se souvient des derniers échanges : « et Kofi aussi » ou « non, 12 000 » sont
compris dans leur contexte.

### Des documents au nom de la boutique

Chaque document est un ticket de papier au style Kayé, envoyé en image et transféré par le commerçant
à son client : le nom et le logo de la boutique en haut, un sceau Kayé discret en bas. Ci-dessous : un
reçu, un bilan de la semaine avec une barre par jour, le stock avec le nombre de jours qu'il tiendra,
une quittance tamponnée « SOLDÉ ».

<p align="center"><img src="docs/img/documents.png" alt="Un reçu, un bilan de la semaine, un état du stock et une quittance, tels que Kayé les envoie" width="100%"></p>

### Deux sortes de cahiers

La plupart des boutiques notent les ventes du jour en **produits et prix, sans nom de client** : elles
ont besoin de leurs totaux, pas de reçus. Les boutiques en ligne ou sur commande notent un **nom de
client ou d'entreprise**, parce qu'elles lui doivent un reçu. Kayé lit les deux à partir d'une photo
prise au téléphone, utilise la date écrite sur la page, et ignore les lignes barrées et le total.

Sur une vraie page de registre écrite à la main et photographiée au téléphone, tous les montants et la
date ont été lus correctement ; quelques noms de produits sont revenus marqués ❓, et le commerçant les
corrige avec **Corriger**, avec ses propres mots.

## Pour commencer

### Commerçant : 2 minutes, rien à installer

1. Écrivez **« Bonjour »** au [+228 71 67 45 79](https://wa.me/22871674579?text=Bonjour).
2. Choisissez **Français** ou **English**. Les commerçants d'Afrique de l'Ouest francophone utilisent
   le français ; **l'anglais est là pour les juges** du hackathon : on peut écrire ou parler en
   anglais, et chaque réponse est traduite (les tickets en image restent en français). Écrivez
   « langue » à tout moment pour changer.
3. Répondez avec le nom de votre boutique, par exemple « Chez Afi ».
4. Envoyez votre première opération : un vocal « J'ai vendu 2 sacs de riz à Ama à 12 000 le sac, elle
   a payé 20 000 », ou la photo de la page du jour de votre cahier.
5. Vérifiez le récapitulatif et appuyez sur **Oui**. Le reçu arrive, prêt à transférer.
6. Demandez « bilan » le soir, « stock » avant de commander, « qui me doit ? » pour relancer.

Les photos se lisent mieux à plat, bien éclairées, la page entière dans le cadre. Pour mettre votre
logo, envoyez-le en photo avec la légende « logo ». Pour tout effacer : « supprimer mes données ».

### Développeur

Prérequis : Python 3.12, [uv](https://docs.astral.sh/uv/), un compte [Modal](https://modal.com), une
app Meta avec WhatsApp, un Postgres Supabase et un bucket Cloudflare R2. En local, les documents ont
besoin de Chromium, Chrome ou Edge, et les vocaux de ffmpeg. Linux, macOS et Windows fonctionnent.

```bash
uv sync
cp .env.example .env              # remplir les valeurs
uv run pytest                     # webhook et documents ; les tests de parcours demandent TEST_DATABASE_URL
```

Les tests de parcours et du cahier tournent sur un vrai Postgres :

```bash
docker run -d --name kaye-pg -e POSTGRES_PASSWORD=kaye -p 127.0.0.1:54329:5432 postgres:17
docker exec kaye-pg psql -U postgres -c "create database kaye_test"
TEST_DATABASE_URL=postgresql://postgres:kaye@127.0.0.1:54329/kaye_test uv run pytest
```

Sous Windows PowerShell, définissez d'abord la variable : `$env:TEST_DATABASE_URL = "postgresql://…"`.

Déployer :

```bash
uv run alembic upgrade head                                         # DATABASE_URL du .env
uv run modal setup                                                  # une seule fois
uv run modal secret create kaye-secrets --from-dotenv .env --force
uv run modal deploy modal_app.py                                    # URL stable + tâches horaires
```

Ensuite, dans le tableau de bord Meta (WhatsApp → Configuration → Webhook), indiquez l'URL
`https://<votre-url-modal>/webhook` et le jeton `WHATSAPP_VERIFY_TOKEN`, puis abonnez-vous à
`messages`. `uv run python -m scripts.whatsapp_setup <url>` le fait et vérifie le compte.

**Essayer sans WhatsApp :** rejouer une conversation contre le vrai agent et les vrais modèles.

```bash
uv run python -m scripts.replay tests/fixtures/conversations/demo.txt --db postgresql://localhost/kaye_scratch
```

## Les modèles Meta utilisés

| Modèle | Rôle |
| --- | --- |
| **Muse Spark 1.3** | Comprend chaque message et choisit les outils (`reasoning_effort=minimal`) ; lit les pages manuscrites et les captures mobile money (`low`, sur une photo nettoyée) |
| **Muse Voice Transcribe 1.0** | Les vocaux en français, orientés vers le vocabulaire du marché (tas, bol, sac, T-Money, Flooz…) |
| **SAM 3.1** | Compte les articles sur une photo de stock |
| **Muse Image 1.0** | Dessine les logos des boutiques |

Les raccourcis et les boutons (« bilan », « stock », « qui me doit ? ») n'utilisent aucun modèle.
`scripts/handwriting_eval.py` compare les façons de lire l'écriture manuscrite sur n'importe quelles
photos.

**Fichiers clés :** `app/agent/` (consignes, outils, boucle de l'agent) · `app/db/ledger.py` (le seul
endroit où naissent les écritures) · `app/documents/templates/` (la famille ticket) · `app/receipts.py`
(HTML → PNG) · `app/images.py` (nettoyage des photos) · `app/jobs.py` (tâches horaires).

## La marque

<p align="center"><img src="docs/img/logo.png" alt="Logo Kayé : le cauri et le mot kayé" width="100%"></p>

Le symbole est un **cauri**, la monnaie historique de l'Afrique de l'Ouest. Son ouverture est dessinée
comme un zigzag de dents qui se lit aussi comme une onde de voix : Kayé écoute, puis écrit. La
signature le dit : « Parle. Kayé note. »

<p align="center"><img src="docs/img/palette-fr.png" alt="Palette : Nuit de Lomé #14111B, Cauri #F5E9D6, Solaire #FF7A1F, Latérite #B84A1E, Lagune #17705F" width="100%"></p>

Chaque couleur garde un seul sens partout : **Latérite**, ce qui est encore dû ; **Lagune**, ce qui est
réglé ; **Solaire**, ce qui appelle à agir. Titres et montants en **Bricolage Grotesque**, texte en
**Inter** ; les montants s'écrivent toujours `148 500 FCFA`.

| Élément | Fichier |
| --- | --- |
| Photo de profil (WhatsApp, Facebook, Instagram), 2048 px | [`profile-solaire-2048.png`](assets/brand/profile-solaire-2048.png) · [`profile-night-2048.png`](assets/brand/profile-night-2048.png) |
| Logo, symbole, logotype, icônes (SVG) | [`assets/brand/`](assets/brand) |
| Les documents, en direct sur un canevas local | `uv run uvicorn design.server:app --reload --port 8765` |

`uv run python -m scripts.brand_export` régénère les logos, les photos de profil et toutes les images de ce README.

## Confidentialité et sécurité

- Chaque numéro WhatsApp est un utilisateur, rattaché à une seule boutique ; chaque requête est limitée à sa boutique.
- Les webhooks sont authentifiés (`X-Hub-Signature-256`) et dédoublonnés par identifiant de message.
- La sécurité par ligne (Row Level Security) est active sur toutes les tables : l'API publique de Supabase ne voit rien.
- Vocaux, photos, reçus et logos sont rangés dans un bucket R2 privé.
- Les données des commerçants ne servent jamais à entraîner des modèles (aucun modèle « contributor »).
- Kayé n'écrit jamais aux clients du commerçant : il prépare le texte, le commerçant l'envoie.
- « supprimer mes données » efface les écritures, utilisateurs et fichiers d'une boutique, après un oui.
- Un quota quotidien par boutique, un budget quotidien global et une liste de blocage protègent le numéro public.

## Construit pendant le hackathon

Tout le code de ce dépôt a été écrit pendant l'événement (26 octobre – 4 novembre 2026) ; voir
l'historique des commits. La photo d'étagère `tests/fixtures/images/shelf_rice.jpg` a été générée par
IA (Muse Image) pour les tests.

## Licence

MIT
