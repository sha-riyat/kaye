/**
 * Every item of the design canvas, kept in source. Add, duplicate, rename or remove items here.
 * To try another version, add a new entry with a new id and a new readable name; keep the
 * original. Positions are only the first layout: the canvas remembers where items were moved,
 * keyed by id.
 */
import HeroComptoir from "./variants/HeroComptoir.astro";
import HeroCauri from "./variants/HeroCauri.astro";
import HeroCahier from "./variants/HeroCahier.astro";
import HowItWorks from "../components/sections/HowItWorks.astro";
import TwoNotebooks from "../components/sections/TwoNotebooks.astro";
import Features from "../components/sections/Features.astro";
import Documents from "../components/sections/Documents.astro";
import Closing from "../components/sections/Closing.astro";

export interface CanvasItem {
  id: string; // stable, never reused
  name: string; // unique and readable; copied when the label is clicked
  component: unknown;
  w: number;
  h: number;
  x: number;
  y: number;
}

const DESKTOP = 1440;
const MOBILE = 390;
const COL = DESKTOP + 160;

export const ITEMS: CanvasItem[] = [
  // Row 1: three heroes, each at desktop and phone width.
  { id: "hero-comptoir", name: "Héros · Comptoir (nuit)", component: HeroComptoir, w: DESKTOP, h: 860, x: 0, y: 0 },
  { id: "hero-comptoir-mobile", name: "Héros · Comptoir (nuit) · mobile", component: HeroComptoir, w: MOBILE, h: 1340, x: 0, y: 1000 },
  { id: "hero-cauri", name: "Héros · Cauri (crème)", component: HeroCauri, w: DESKTOP, h: 1300, x: COL, y: 0 },
  { id: "hero-cauri-mobile", name: "Héros · Cauri (crème) · mobile", component: HeroCauri, w: MOBILE, h: 1660, x: COL, y: 1440 },
  { id: "hero-cahier", name: "Héros · Du cahier à WhatsApp", component: HeroCahier, w: DESKTOP, h: 1180, x: 2 * COL, y: 0 },
  { id: "hero-cahier-mobile", name: "Héros · Du cahier à WhatsApp · mobile", component: HeroCahier, w: MOBILE, h: 2400, x: 2 * COL, y: 1320 },

  // Row 2: the sections that follow the hero, in page order.
  { id: "section-comment", name: "Section · Comment ça marche", component: HowItWorks, w: DESKTOP, h: 820, x: 0, y: 3900 },
  { id: "section-deux-cahiers", name: "Section · Deux façons de tenir boutique", component: TwoNotebooks, w: DESKTOP, h: 1060, x: COL, y: 3900 },
  { id: "section-fonctions", name: "Section · Tout ce que Kayé tient", component: Features, w: DESKTOP, h: 1080, x: 2 * COL, y: 3900 },
  { id: "section-documents", name: "Section · Les bons papiers", component: Documents, w: DESKTOP, h: 900, x: 0, y: 5200 },
  { id: "section-fin", name: "Section · Confiance, appel et pied de page", component: Closing, w: DESKTOP, h: 1260, x: COL, y: 5200 },
];

const ids = new Set(ITEMS.map((i) => i.id));
const names = new Set(ITEMS.map((i) => i.name));
if (ids.size !== ITEMS.length || names.size !== ITEMS.length) throw new Error("canvas ids and names must be unique");
