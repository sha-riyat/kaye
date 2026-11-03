/** Every word of the landing page, in French (the default, at /) and English (at /en). The tickets
 * shown on the page are real Kayé documents and stay in French in both. */
import { WHATSAPP, WHATSAPP_EN } from "./site";

export type Lang = "fr" | "en";

export const copy = {
  fr: {
    home: "/",
    other: { href: "/en", label: "English" },
    privacy: "/confidentialite",
    wa: WHATSAPP,
    meta: {
      title: "Kayé · Votre cahier de boutique, dans WhatsApp",
      description: "Dites-le, Kayé le note. Ventes, crédits, stock, dépenses : toute la gestion d'une boutique dans WhatsApp, à la voix.",
    },
    nav: { how: "Comment ça marche", promise: "La promesse", privacy: "Confidentialité", write: "Écrire à Kayé", home: "Kayé, accueil", label: "Navigation principale" },
    hero: {
      a: "Dites-le.",
      b: "Kayé le note.",
      sub: "Votre cahier de boutique, dans WhatsApp : ventes, crédits, stock, dépenses. À la voix.",
      alt: "Un commerçant en tablier consulte son téléphone dans sa boutique",
      three: [
        ["Rien à installer", "WhatsApp est déjà sur le téléphone."],
        ["Rien à apprendre", "On parle comme au comptoir."],
        ["Rien de perdu", "Le cahier ne se mouille plus."],
      ],
    },
    proof: {
      label: "Une note vocale devient un reçu",
      reply: ["Ama : 3 articles, ", "33 000 FCFA", ". Payé 25 000, reste ", "8 000", ". Voici son reçu."],
      alt: "Le reçu d'Ama, au nom de la boutique",
    },
    notebook: {
      a: "Le commerce d'ici",
      b: "tient sur ",
      c: "un cahier.",
      alt: "Un jeune commerçant écrit dans son cahier, dans sa boutique",
      p1: "Le stock, les ventes, les crédits, le fournisseur à payer vendredi, la recette du jour : tout passe par un cahier à spirale et par WhatsApp. Les logiciels de gestion ont été pensés pour des bureaux. Les commerçants ne les ont pas adoptés.",
      p2: "Kayé ne leur demande pas de changer d'outil. Il s'installe là où ils sont déjà, dans WhatsApp, et tient le cahier à leur place : on lui parle, on lui envoie une photo, il note, calcule et rappelle.",
    },
    day: {
      a: "Du premier client",
      b: "au dernier franc.",
      steps: [
        { h: "07:30", k: "Arrivage", said: "« Koffi a livré la marchandise. Je lui dois 180 000, vendredi prochain. »", kaye: "Arrivage noté, stock à jour. Dette Koffi : 180 000 FCFA, je vous le rappelle la veille." },
        { h: "09:10", k: "Vente à crédit", said: "🎤 Note vocale · 0:09", kaye: "Ama : 3 articles, 33 000. Payé 25 000, reste 8 000. Voici son reçu, à transférer.", alt: "Le reçu d'Ama, au nom de la boutique" },
        { h: "11:45", k: "Dépense", said: "« Transport 3 500, sachets 1 500. »", kaye: "Deux dépenses notées. Sorties du jour : 5 000 FCFA." },
        { h: "14:20", k: "Paiement", said: "↪ Paiement mobile money transféré", kaye: "Kofi Mensah a payé 12 500. Sa dette est soldée : voici sa quittance.", alt: "La quittance de Kofi, tamponnée soldé" },
        { h: "16:00", k: "Stock", said: "« Qu'est-ce qui va manquer ? »", kaye: "Deux articles passent sous le seuil. Au rythme de la semaine, plus rien mardi : à recommander.", alt: "L'état du stock avec les jours restants" },
        { h: "20:00", k: "Bilan du soir", said: "Envoyé par Kayé, chaque soir", kaye: "Ventes 148 500 · encaissé 112 000 · à crédit 36 500. Trois clients à relancer.", alt: "Le bilan du jour" },
      ],
    },
    promise: {
      a: "Ce qui est dit",
      b: "est noté.",
      said: "« Elle me doit encore 8 000. »",
      label: "Une phrase dite devient une ligne du cahier",
      ledger: ["Crédits", "Aujourd'hui"],
      items: [
        ["Vision", "Que chaque commerçant d'Afrique de l'Ouest sache, chaque soir, où en est sa boutique."],
        ["Mission", "Tenir la gestion des petits commerces là où ils travaillent déjà : dans WhatsApp, à la voix."],
        ["Pour qui", "Boutiques, vendeuses du marché, grossistes de quartier, artisans, pharmacies, e-commerçants sur WhatsApp. Lomé d'abord, puis la sous-région francophone."],
      ],
    },
    shop: {
      a: "Toute la boutique,",
      b: "dans une conversation.",
      p: "Kayé n'est pas un carnet de reçus. C'est l'assistant qui tient tout ce qu'un logiciel de gestion promettait, sans écran à apprendre : on lui dit, il note.",
      items: [
        ["Ventes", "« J'ai vendu pour 33 000 à Ama. »"],
        ["Crédits", "« Elle me doit encore 8 000. »"],
        ["Paiements", "Un paiement mobile money transféré solde la dette."],
        ["Stock", "« La marchandise est arrivée. Qu'est-ce qui va manquer ? »"],
        ["Dépenses et caisse", "« J'ai payé 3 500 de transport. »"],
        ["Fournisseurs", "« Je dois 50 000 à Koffi, vendredi. »"],
        ["Équipe", "« Ajoute mon vendeur Kodjo. »"],
        ["Bilans", "« Fais-moi le bilan de la semaine. »"],
        ["Relances", "« Qui me doit ? » La relance est prête à envoyer."],
        ["Documents", "Reçus, factures, relevés, au nom de la boutique."],
      ],
    },
    values: {
      a: "Quatre ",
      b: "valeurs.",
      p: "Elles décident de tout, d'un mot dans un message comme d'une fonction du produit. Si un choix les contredit, c'est le choix qui change.",
      items: [
        ["Fidèle", "On note exactement ce qui a été dit, rien de plus.", "Chaque écriture attend le « Oui ». Une correction ne s'efface jamais, elle s'ajoute."],
        ["Proche", "On parle la langue du comptoir.", "La pièce, le tas, le carton, le yard. Des FCFA. Un français simple, des phrases courtes."],
        ["Discret", "Les comptes d'une boutique ne regardent qu'elle.", "Ni publicité, ni revente, ni entraînement de modèles. Kayé n'écrit jamais à un client à votre place."],
        ["Léger", "Rien à installer, rien à apprendre.", "WhatsApp suffit. Ça marche sur un petit téléphone et une connexion faible."],
      ],
    },
    call: {
      alt: "Un jeune boutiquier à son comptoir",
      sticker: ["Ici, on note", "avec Kayé."],
      a: "Dites bonjour",
      b: "à ",
      p: ["Écrivez « Bonjour » au ", ", ou scannez le code. Choisissez Français ou English, donnez le nom de votre boutique, et dites votre première vente."],
      open: "Ouvrir WhatsApp",
      qr: "QR code vers la conversation WhatsApp de Kayé",
      demo: "Mode démo : utilisez des données fictives.",
    },
    footer: { promise: ["Ce qui est dit ", "est noté."], credits: "Fait à Lomé · Photos Pexels et Unsplash, au filtre Solaire" },
  },

  en: {
    home: "/en",
    other: { href: "/", label: "Français" },
    privacy: "/en/privacy",
    wa: WHATSAPP_EN,
    meta: {
      title: "Kayé · Your shop's notebook, in WhatsApp",
      description: "Say it, Kayé writes it down. Sales, credit, stock, expenses: a whole shop's bookkeeping in WhatsApp, by voice.",
    },
    nav: { how: "How it works", promise: "The promise", privacy: "Privacy", write: "Message Kayé", home: "Kayé, home", label: "Main navigation" },
    hero: {
      a: "Say it.",
      b: "Kayé writes it down.",
      sub: "Your shop's notebook, in WhatsApp: sales, credit, stock, expenses. By voice.",
      alt: "A shopkeeper in an apron checks his phone in his shop",
      three: [
        ["Nothing to install", "WhatsApp is already on the phone."],
        ["Nothing to learn", "Talk as you would at the counter."],
        ["Nothing lost", "This notebook never gets wet."],
      ],
    },
    proof: {
      label: "A voice note becomes a receipt",
      reply: ["Ama: 3 items, ", "33,000 FCFA", ". Paid 25,000, ", "8,000", " left. Here is her receipt."],
      alt: "Ama's receipt, in the shop's name",
    },
    notebook: {
      a: "Business here",
      b: "runs on ",
      c: "a notebook.",
      alt: "A young shopkeeper writes in his notebook, in his shop",
      p1: "Stock, sales, credit, the supplier to pay on Friday, the day's takings: it all goes through a spiral notebook and WhatsApp. Bookkeeping software was designed for offices. Shopkeepers never took to it.",
      p2: "Kayé doesn't ask them to change tools. It settles where they already are, in WhatsApp, and keeps the notebook for them: talk to it, send it a photo, it writes down, adds up and reminds.",
    },
    day: {
      a: "From the first customer",
      b: "to the last franc.",
      steps: [
        { h: "07:30", k: "Delivery", said: "“Koffi delivered the goods. I owe him 180,000, next Friday.”", kaye: "Delivery noted, stock updated. Owed to Koffi: 180,000 FCFA, I'll remind you the day before." },
        { h: "09:10", k: "Sale on credit", said: "🎤 Voice note · 0:09", kaye: "Ama: 3 items, 33,000. Paid 25,000, 8,000 left. Here is her receipt, ready to forward.", alt: "Ama's receipt, in the shop's name" },
        { h: "11:45", k: "Expense", said: "“Transport 3,500, bags 1,500.”", kaye: "Two expenses noted. Money out today: 5,000 FCFA." },
        { h: "14:20", k: "Payment", said: "↪ Mobile money payment forwarded", kaye: "Kofi Mensah paid 12,500. His debt is settled: here is his receipt.", alt: "Kofi's settlement, stamped paid" },
        { h: "16:00", k: "Stock", said: "“What's about to run out?”", kaye: "Two items fall below the threshold. At this week's pace, none left by Tuesday: time to reorder.", alt: "Stock levels with the days left" },
        { h: "20:00", k: "Evening summary", said: "Sent by Kayé, every evening", kaye: "Sales 148,500 · cashed 112,000 · on credit 36,500. Three customers to remind.", alt: "The day's summary" },
      ],
    },
    promise: {
      a: "What is said",
      b: "is written down.",
      said: "“She still owes me 8,000.”",
      label: "A spoken sentence becomes a line in the notebook",
      ledger: ["Credit", "Today"],
      items: [
        ["Vision", "That every West African shopkeeper knows, every evening, where their shop stands."],
        ["Mission", "Keep small shops' books where they already work: in WhatsApp, by voice."],
        ["For whom", "Shops, market sellers, neighbourhood wholesalers, craftspeople, pharmacies, WhatsApp sellers. Lomé first, then French-speaking West Africa."],
      ],
    },
    shop: {
      a: "The whole shop,",
      b: "in one conversation.",
      p: "Kayé isn't a receipt book. It's the assistant that keeps everything bookkeeping software promised, with no screen to learn: you say it, it writes it down.",
      items: [
        ["Sales", "“I sold 33,000 worth to Ama.”"],
        ["Credit", "“She still owes me 8,000.”"],
        ["Payments", "A forwarded mobile money payment settles the debt."],
        ["Stock", "“The goods arrived. What's about to run out?”"],
        ["Expenses and cash", "“I paid 3,500 for transport.”"],
        ["Suppliers", "“I owe Koffi 50,000, Friday.”"],
        ["Team", "“Add my salesman Kodjo.”"],
        ["Summaries", "“Give me this week's summary.”"],
        ["Reminders", "“Who owes me?” The reminder is ready to send."],
        ["Documents", "Receipts, invoices, statements, in the shop's name."],
      ],
    },
    values: {
      a: "Four ",
      b: "values.",
      p: "They decide everything, from a word in a message to a feature of the product. If a choice goes against them, the choice changes.",
      items: [
        ["Faithful", "We write down exactly what was said, nothing more.", "Every entry waits for a “Yes”. A correction is never erased, it's added."],
        ["Close", "We speak the language of the counter.", "The piece, the pile, the box, the yard. FCFA. Plain words, short sentences."],
        ["Discreet", "A shop's books are its own business.", "No ads, no reselling, no model training. Kayé never messages a customer in your place."],
        ["Light", "Nothing to install, nothing to learn.", "WhatsApp is enough. It works on a small phone and a weak connection."],
      ],
    },
    call: {
      alt: "A young shopkeeper at his counter",
      sticker: ["Here, we keep", "books with Kayé."],
      a: "Say hello",
      b: "to ",
      p: ["Write “Hello” to ", ", or scan the code. Pick English or Français, give your shop's name, and tell Kayé your first sale."],
      open: "Open WhatsApp",
      qr: "QR code to Kayé's WhatsApp conversation",
      demo: "Demo mode: use made-up data.",
    },
    footer: { promise: ["What is said ", "is written down."], credits: "Made in Lomé · Photos from Pexels and Unsplash, with the Solaire filter" },
  },
} as const;

export type Copy = (typeof copy)[Lang];
