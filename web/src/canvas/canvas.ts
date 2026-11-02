// Kayé site canvas: live previews of the landing page variants, named, movable, zoomable.
// What is on the canvas (items, names, sizes) comes from registry.ts and is rendered by the page.
// This script only moves the camera and the items, and saves both, keyed by stable item id.
// Adapted from the documents canvas (design/canvas/canvas.js).

const STORAGE_KEY = "kaye-web-canvas:site";
const STORAGE_VERSION = 1;
const MIN_Z = 0.03;
const MAX_Z = 4;
const LIMIT = 1e6;
const HEADER = 48; // label row above each preview, in screen px
const DEFAULT_CAMERA = { x: 48, y: 96, z: 0.3 };

interface Item { id: string; name: string; w: number; h: number; el: HTMLElement; header: HTMLElement; status: HTMLElement }
interface Camera { x: number; y: number; z: number }
type Gesture =
  | { kind: "pan"; pointerId: number; sx: number; sy: number; ox: number; oy: number; moved: boolean }
  | { kind: "move"; pointerId: number; id: string; sx: number; sy: number; ox: number; oy: number; moved: boolean };

const viewport = document.getElementById("viewport") as HTMLElement;
const world = document.getElementById("world") as HTMLElement;
const zoomLevel = document.getElementById("zoom-level") as HTMLOutputElement;
const announce = document.getElementById("announce") as HTMLElement;
const fallback = document.getElementById("fallback") as HTMLElement;
const fallbackText = document.getElementById("fallback-text") as HTMLInputElement;

const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v) && Math.abs(v) < LIMIT;
const clampZ = (z: number) => Math.min(MAX_Z, Math.max(MIN_Z, z));
const clampPos = (v: number) => Math.max(-LIMIT + 1, Math.min(LIMIT - 1, v));

const camera: Camera = { ...DEFAULT_CAMERA };
const positions = new Map<string, { x: number; y: number }>();
const items: Item[] = [...world.querySelectorAll<HTMLElement>(".item")].map((el) => ({
  id: el.dataset.id!,
  name: el.dataset.name!,
  w: Number(el.dataset.w),
  h: Number(el.dataset.h),
  el,
  header: el.querySelector(".item-header") as HTMLElement,
  status: el.querySelector(".item-status") as HTMLElement,
}));
let frame = 0;
let saveTimer = 0;
let gesture: Gesture | null = null;
let spaceHeld = false;
let swallowClick = false;

// ---------- rendering: at most one transform write per frame ----------
function scheduleFrame() {
  if (frame) return;
  frame = requestAnimationFrame(() => {
    frame = 0;
    world.style.transform = `translate(${camera.x}px, ${camera.y}px) scale(${camera.z})`;
    zoomLevel.textContent = `${Math.round(camera.z * 100)} %`;
    for (const it of items) it.header.style.transform = `scale(${1 / camera.z})`;
  });
}
function placeItem(id: string) {
  const p = positions.get(id);
  const it = items.find((i) => i.id === id);
  if (p && it) it.el.style.transform = `translate(${p.x}px, ${p.y}px)`;
}

// ---------- saved layout: camera and positions only ----------
function loadLayout(): { camera?: Camera; positions?: Record<string, { x: number; y: number }> } | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw || raw.length > 200_000) return null;
    const doc = JSON.parse(raw);
    return doc && doc.v === STORAGE_VERSION ? doc : null;
  } catch {
    return null;
  }
}
function saveNow() {
  clearTimeout(saveTimer);
  saveTimer = 0;
  try {
    const pos: Record<string, { x: number; y: number } | undefined> = {};
    for (const it of items) pos[it.id] = positions.get(it.id);
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ v: STORAGE_VERSION, camera, positions: pos }));
  } catch {
    /* storage unavailable or full: the canvas keeps working without it */
  }
}
function saveSoon() {
  clearTimeout(saveTimer);
  saveTimer = window.setTimeout(saveNow, 400);
}

// ---------- camera ----------
function bounds() {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const it of items) {
    const p = positions.get(it.id)!;
    minX = Math.min(minX, p.x);
    minY = Math.min(minY, p.y - HEADER / camera.z);
    maxX = Math.max(maxX, p.x + it.w);
    maxY = Math.max(maxY, p.y + it.h);
  }
  return items.length ? { minX, minY, maxX, maxY } : null;
}
function zoomAt(px: number, py: number, factor: number) {
  const z = clampZ(camera.z * factor);
  const k = z / camera.z;
  camera.x = px - (px - camera.x) * k;
  camera.y = py - (py - camera.y) * k;
  camera.z = z;
  scheduleFrame();
}
function zoomCenter(factor: number) {
  const r = viewport.getBoundingClientRect();
  zoomAt(r.width / 2, r.height / 2, factor);
  saveSoon();
}
function fitAll() {
  const b = bounds();
  if (!b) return;
  const r = viewport.getBoundingClientRect();
  const pad = 64;
  const z = clampZ(Math.min((r.width - 2 * pad) / (b.maxX - b.minX), (r.height - 2 * pad - HEADER) / (b.maxY - b.minY)));
  camera.z = z;
  camera.x = (r.width - (b.maxX - b.minX) * z) / 2 - b.minX * z;
  camera.y = (r.height - (b.maxY - b.minY) * z) / 2 - b.minY * z + HEADER / 2;
  scheduleFrame();
  saveSoon();
}
function resetCamera() {
  Object.assign(camera, DEFAULT_CAMERA);
  scheduleFrame();
  saveSoon();
}

// ---------- copying names ----------
async function copyName(it: Item) {
  if (swallowClick) return;
  try {
    if (!navigator.clipboard?.writeText) throw new Error("no clipboard");
    await navigator.clipboard.writeText(it.name);
    it.status.textContent = "Copié";
    setTimeout(() => (it.status.textContent = ""), 1400);
  } catch {
    fallbackText.value = it.name;
    fallback.hidden = false;
    fallbackText.focus();
    fallbackText.select();
  }
}
document.getElementById("fallback-close")!.addEventListener("click", () => (fallback.hidden = true));

// ---------- keyboard movement of items ----------
function moveWithKeys(e: KeyboardEvent, id: string) {
  const step = e.shiftKey ? 80 : 16;
  const d = ({ ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] } as Record<string, number[]>)[e.key];
  if (!d) return;
  e.preventDefault();
  const p = positions.get(id)!;
  positions.set(id, { x: clampPos(p.x + d[0]), y: clampPos(p.y + d[1]) });
  placeItem(id);
  saveSoon();
}

for (const it of items) {
  it.el.querySelector(".item-label")!.addEventListener("click", () => copyName(it));
  it.el.querySelector(".item-handle")!.addEventListener("keydown", (e) => moveWithKeys(e as KeyboardEvent, it.id));
}

// Links inside previews are part of the design, not navigation: say where they lead, stay here.
world.addEventListener("click", (e) => {
  const link = (e.target as Element).closest?.(".item-preview a[href]") as HTMLAnchorElement | null;
  if (!link) return;
  e.preventDefault();
  if (swallowClick) return;
  const it = items.find((i) => i.el.contains(link));
  if (it) {
    it.status.textContent = `Lien : ${link.getAttribute("href")}`;
    setTimeout(() => (it.status.textContent = ""), 2400);
  }
});

// ---------- gestures ----------
viewport.addEventListener(
  "pointerdown",
  (e) => {
    const background = e.target === viewport || e.target === world;
    const wantsPan = e.button === 1 || (e.button === 0 && (spaceHeld || background));
    if (wantsPan) {
      e.preventDefault(); // also blocks middle-click autoscroll
      e.stopPropagation();
      gesture = { kind: "pan", pointerId: e.pointerId, sx: e.clientX, sy: e.clientY, ox: camera.x, oy: camera.y, moved: false };
      viewport.setPointerCapture(e.pointerId);
      if (background) viewport.focus({ preventScroll: true });
      return;
    }
    const handle = (e.target as Element).closest?.(".item-handle") as HTMLElement | null;
    if (e.button === 0 && handle) {
      const id = (handle.closest(".item") as HTMLElement).dataset.id!;
      const p = positions.get(id)!;
      e.preventDefault();
      gesture = { kind: "move", pointerId: e.pointerId, id, sx: e.clientX, sy: e.clientY, ox: p.x, oy: p.y, moved: false };
      handle.setPointerCapture(e.pointerId);
    }
  },
  true,
);
window.addEventListener("pointermove", (e) => {
  if (!gesture || e.pointerId !== gesture.pointerId) return;
  const dx = e.clientX - gesture.sx;
  const dy = e.clientY - gesture.sy;
  if (Math.abs(dx) + Math.abs(dy) > 3) gesture.moved = true;
  if (gesture.kind === "pan") {
    camera.x = gesture.ox + dx;
    camera.y = gesture.oy + dy;
    scheduleFrame();
  } else {
    positions.set(gesture.id, { x: clampPos(gesture.ox + dx / camera.z), y: clampPos(gesture.oy + dy / camera.z) });
    placeItem(gesture.id);
  }
});
function endGesture(e?: PointerEvent) {
  if (!gesture || (e && e.pointerId !== undefined && e.pointerId !== gesture.pointerId)) return;
  if (gesture.moved) {
    swallowClick = true; // a pan or a drag must not also copy a label or follow a link
    setTimeout(() => (swallowClick = false), 0);
  }
  gesture = null;
  saveSoon();
}
window.addEventListener("pointerup", endGesture);
window.addEventListener("pointercancel", endGesture);
viewport.addEventListener("lostpointercapture", (e) => endGesture(e));
viewport.addEventListener("auxclick", (e) => e.button === 1 && e.preventDefault());

viewport.addEventListener(
  "wheel",
  (e) => {
    e.preventDefault();
    const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? viewport.clientHeight : 1;
    if (e.ctrlKey || e.metaKey) {
      const r = viewport.getBoundingClientRect();
      zoomAt(e.clientX - r.left, e.clientY - r.top, Math.exp(-e.deltaY * unit * 0.0025));
    } else {
      camera.x -= e.deltaX * unit;
      camera.y -= e.deltaY * unit;
      scheduleFrame();
    }
    saveSoon();
  },
  { passive: false },
);

const isEditable = (el: Element | null) =>
  !!el && ((el as HTMLElement).isContentEditable || /^(INPUT|TEXTAREA|SELECT|BUTTON|A)$/.test(el.tagName));
window.addEventListener("keydown", (e) => {
  if (e.code === "Space" && !e.repeat) {
    const active = document.activeElement;
    if (active === document.body || active === viewport) {
      spaceHeld = true;
      e.preventDefault();
    }
  }
});
window.addEventListener("keyup", (e) => {
  if (e.code === "Space") spaceHeld = false;
});
const clearKeys = () => {
  spaceHeld = false;
  endGesture();
};
window.addEventListener("blur", clearKeys);
document.addEventListener("visibilitychange", () => document.hidden && clearKeys());

viewport.addEventListener("keydown", (e) => {
  if (e.target !== viewport || isEditable(e.target as Element)) return;
  const pan = 80;
  const actions: Record<string, () => void> = {
    "+": () => zoomCenter(1.2),
    "=": () => zoomCenter(1.2),
    "-": () => zoomCenter(1 / 1.2),
    "0": resetCamera,
    "1": fitAll,
    ArrowLeft: () => (camera.x += pan),
    ArrowRight: () => (camera.x -= pan),
    ArrowUp: () => (camera.y += pan),
    ArrowDown: () => (camera.y -= pan),
  };
  const run = actions[e.key];
  if (!run) return;
  e.preventDefault();
  run();
  scheduleFrame();
  saveSoon();
});

document.getElementById("zoom-in")!.addEventListener("click", () => zoomCenter(1.2));
document.getElementById("zoom-out")!.addEventListener("click", () => zoomCenter(1 / 1.2));
document.getElementById("fit")!.addEventListener("click", fitAll);
document.getElementById("reset")!.addEventListener("click", resetCamera);

// Reveal an offscreen focused item through the camera, never by native scrolling.
world.addEventListener("focusin", (e) => {
  const el = (e.target as Element).closest(".item") as HTMLElement | null;
  if (!el) return;
  const p = positions.get(el.dataset.id!)!;
  const r = viewport.getBoundingClientRect();
  const sx = camera.x + p.x * camera.z;
  const sy = camera.y + p.y * camera.z;
  if (sx < 0 || sy < HEADER || sx > r.width - 40 || sy > r.height - 40) {
    camera.x = 64 - p.x * camera.z;
    camera.y = 96 - p.y * camera.z;
    scheduleFrame();
  }
  viewport.scrollTop = 0;
  viewport.scrollLeft = 0;
});
window.addEventListener("pagehide", () => saveTimer && saveNow());

// ---------- start ----------
const saved = loadLayout();
if (saved?.camera && finite(saved.camera.x) && finite(saved.camera.y) && finite(saved.camera.z)) {
  camera.x = saved.camera.x;
  camera.y = saved.camera.y;
  camera.z = clampZ(saved.camera.z);
}
for (const it of items) {
  const s = saved?.positions?.[it.id];
  const el = it.el;
  positions.set(it.id, s && finite(s.x) && finite(s.y) ? { x: s.x, y: s.y } : { x: Number(el.dataset.x), y: Number(el.dataset.y) });
  placeItem(it.id);
}
scheduleFrame();
if (!saved) requestAnimationFrame(() => requestAnimationFrame(fitAll));
announce.textContent = `${items.length} aperçus`;
