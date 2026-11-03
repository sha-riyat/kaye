/**
 * Every item of the design canvas, kept in source: the landing page, chosen among full-page
 * versions, in each language at desktop and phone width. To try another version, add a new entry
 * with a new id and a new readable name; keep the original. Positions are only the first layout:
 * the canvas remembers where items were moved, keyed by id.
 */
import Landing from "../components/Landing.astro";

export interface CanvasItem {
  id: string; // stable, never reused
  name: string; // unique and readable; copied when the label is clicked
  component: unknown;
  props?: Record<string, unknown>;
  w: number;
  h: number;
  x: number;
  y: number;
}

const DESKTOP = 1440;
const MOBILE = 390;
const GAP = 160;
const COL = DESKTOP + MOBILE + 2 * GAP; // one language per column: desktop, then its phone

export const ITEMS: CanvasItem[] = [
  { id: "v1-journee", name: "Landing · Dites-le, Kayé le note", component: Landing, props: { lang: "fr" }, w: DESKTOP, h: 6600, x: 0, y: 0 },
  { id: "v1-journee-mobile", name: "Landing · Dites-le, Kayé le note · mobile", component: Landing, props: { lang: "fr" }, w: MOBILE, h: 11600, x: DESKTOP + GAP, y: 0 },
  { id: "landing-en", name: "Landing · Say it, Kayé writes it down", component: Landing, props: { lang: "en" }, w: DESKTOP, h: 6600, x: COL, y: 0 },
  { id: "landing-en-mobile", name: "Landing · Say it, Kayé writes it down · mobile", component: Landing, props: { lang: "en" }, w: MOBILE, h: 11600, x: COL + DESKTOP + GAP, y: 0 },
];

const ids = new Set(ITEMS.map((i) => i.id));
const names = new Set(ITEMS.map((i) => i.name));
if (ids.size !== ITEMS.length || names.size !== ITEMS.length) throw new Error("canvas ids and names must be unique");
