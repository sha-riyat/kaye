// Kayé design canvas: live previews of document templates, named, movable, zoomable.
// Content (which items, names, sizes) comes from the registry in source (design/registry.py).
// This file only saves the camera and item positions, keyed by stable id.
(() => {
  "use strict";

  const STORAGE_KEY = "kaye-design-canvas:documents";
  const STORAGE_VERSION = 1;
  const MIN_Z = 0.05;
  const MAX_Z = 4;
  const LIMIT = 1e6;
  const GAP = 80;
  const HEADER = 48; // label row above each preview, in screen px
  const DEFAULT_CAMERA = { x: 48, y: 96, z: 0.35 };

  const viewport = document.getElementById("viewport");
  const world = document.getElementById("world");
  const zoomLevel = document.getElementById("zoom-level");
  const announce = document.getElementById("announce");
  const fallback = document.getElementById("fallback");
  const fallbackText = document.getElementById("fallback-text");

  const camera = { ...DEFAULT_CAMERA };
  let items = []; // registry entries, in order
  const positions = new Map(); // id -> {x, y}
  const nodes = new Map(); // id -> {el, preview, shadow, status, header}
  let frame = 0;
  let saveTimer = 0;
  let gesture = null;
  let spaceHeld = false;
  let swallowClick = false;

  const finite = (v) => typeof v === "number" && Number.isFinite(v) && Math.abs(v) < LIMIT;
  const clampZ = (z) => Math.min(MAX_Z, Math.max(MIN_Z, z));
  const clampPos = (v) => Math.max(-LIMIT + 1, Math.min(LIMIT - 1, v));

  // ---------- rendering: at most one transform write per frame ----------
  function scheduleFrame() {
    if (frame) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      world.style.transform = `translate(${camera.x}px, ${camera.y}px) scale(${camera.z})`;
      world.style.setProperty("--inv-z", String(1 / camera.z));
      zoomLevel.textContent = `${Math.round(camera.z * 100)} %`;
      for (const n of nodes.values()) n.header.style.transform = `scale(${1 / camera.z})`;
    });
  }

  function placeItem(id) {
    const p = positions.get(id);
    const n = nodes.get(id);
    if (p && n) n.el.style.transform = `translate(${p.x}px, ${p.y}px)`;
  }

  // ---------- saved layout (camera + positions only) ----------
  function loadLayout() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw || raw.length > 200_000) return null;
      const doc = JSON.parse(raw);
      return doc && doc.v === STORAGE_VERSION ? doc : null;
    } catch {
      return null;
    }
  }

  function saveSoon() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveNow, 400);
  }

  function saveNow() {
    clearTimeout(saveTimer);
    saveTimer = 0;
    try {
      const pos = {};
      for (const item of items) pos[item.id] = positions.get(item.id);
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ v: STORAGE_VERSION, camera, positions: pos }));
    } catch {
      /* storage unavailable or full: the canvas keeps working without it */
    }
  }

  // ---------- items ----------
  function bounds() {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const item of items) {
      const p = positions.get(item.id);
      minX = Math.min(minX, p.x);
      minY = Math.min(minY, p.y - HEADER / camera.z);
      maxX = Math.max(maxX, p.x + item.w);
      maxY = Math.max(maxY, p.y + item.h);
    }
    return items.length ? { minX, minY, maxX, maxY } : null;
  }

  function buildItem(item) {
    const el = document.createElement("section");
    el.className = "item";
    el.dataset.id = item.id;
    el.setAttribute("aria-label", item.name);

    const header = document.createElement("div");
    header.className = "item-header";

    const handle = document.createElement("button");
    handle.type = "button";
    handle.className = "item-handle";
    handle.setAttribute("aria-label", `Déplacer ${item.name}. Flèches pour déplacer, Maj pour aller plus vite.`);
    handle.title = "Glisser pour déplacer";
    handle.innerHTML =
      '<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><g fill="currentColor">' +
      '<circle cx="4" cy="3" r="1.3"/><circle cx="10" cy="3" r="1.3"/><circle cx="4" cy="7" r="1.3"/>' +
      '<circle cx="10" cy="7" r="1.3"/><circle cx="4" cy="11" r="1.3"/><circle cx="10" cy="11" r="1.3"/></g></svg>';

    const label = document.createElement("button");
    label.type = "button";
    label.className = "item-label";
    label.textContent = item.name;
    label.title = "Cliquer pour copier le nom";

    const status = document.createElement("span");
    status.className = "item-status";
    status.setAttribute("aria-live", "polite");

    header.append(handle, label, status);

    const preview = document.createElement("div");
    preview.className = "item-preview";
    preview.style.width = `${item.w}px`;
    preview.style.height = `${item.h}px`;
    const shadow = preview.attachShadow({ mode: "open" });

    el.append(header, preview);
    world.append(el);
    nodes.set(item.id, { el, preview, shadow, status, header, label });

    label.addEventListener("click", () => copyName(item.id));
    handle.addEventListener("keydown", (e) => moveWithKeys(e, item.id));
  }

  function updateItem(item) {
    const n = nodes.get(item.id);
    n.label.textContent = item.name;
    n.el.setAttribute("aria-label", item.name);
    n.preview.style.width = `${item.w}px`;
    n.preview.style.height = `${item.h}px`;
  }

  async function renderPreview(item) {
    const n = nodes.get(item.id);
    if (!n) return;
    try {
      const res = await fetch(`/preview/${encodeURIComponent(item.id)}`, { cache: "no-store" });
      if (!res.ok) throw new Error(`${res.status}`);
      const doc = new DOMParser().parseFromString(await res.text(), "text/html");
      doc.querySelectorAll("script").forEach((s) => s.remove());
      const content = document.createElement("div");
      content.append(...doc.head.querySelectorAll("style"), ...doc.body.childNodes);
      n.shadow.replaceChildren(...content.childNodes);
    } catch (err) {
      const msg = document.createElement("p");
      msg.className = "item-error";
      msg.textContent = `Aperçu indisponible (${err.message}). Vérifier le gabarit et le serveur.`;
      n.shadow.replaceChildren(msg);
    }
  }

  async function loadRegistry() {
    const res = await fetch("/registry", { cache: "no-store" });
    if (!res.ok) throw new Error(`registry ${res.status}`);
    const next = await res.json();
    return next.filter(
      (i) => typeof i.id === "string" && typeof i.name === "string" && finite(i.w) && finite(i.h) && finite(i.x) && finite(i.y),
    );
  }

  function applyRegistry(next, saved) {
    const nextIds = new Set(next.map((i) => i.id));
    for (const [id, n] of nodes) {
      if (!nextIds.has(id)) {
        n.el.remove();
        nodes.delete(id);
        positions.delete(id);
      }
    }
    const known = items.length ? bounds() : null;
    let freeX = known ? known.maxX + GAP : 0;
    for (const item of next) {
      if (!nodes.has(item.id)) {
        buildItem(item);
        const s = saved && saved.positions && saved.positions[item.id];
        if (s && finite(s.x) && finite(s.y)) positions.set(item.id, { x: s.x, y: s.y });
        else if (known) {
          positions.set(item.id, { x: freeX, y: known.minY + HEADER / camera.z });
          freeX += item.w + GAP;
        } else positions.set(item.id, { x: item.x, y: item.y });
        placeItem(item.id);
      } else updateItem(item);
    }
    items = next;
  }

  // ---------- camera ----------
  function zoomAt(px, py, factor) {
    const z = clampZ(camera.z * factor);
    const k = z / camera.z;
    camera.x = px - (px - camera.x) * k;
    camera.y = py - (py - camera.y) * k;
    camera.z = z;
    scheduleFrame();
  }

  function zoomCenter(factor) {
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
  async function copyName(id) {
    if (swallowClick) return;
    const item = items.find((i) => i.id === id);
    const n = nodes.get(id);
    if (!item || !n) return;
    try {
      if (!navigator.clipboard || !navigator.clipboard.writeText) throw new Error("no clipboard");
      await navigator.clipboard.writeText(item.name);
      n.status.textContent = "Copié";
      setTimeout(() => (n.status.textContent = ""), 1400);
    } catch {
      fallbackText.value = item.name;
      fallback.hidden = false;
      fallbackText.focus();
      fallbackText.select();
    }
  }
  document.getElementById("fallback-close").addEventListener("click", () => (fallback.hidden = true));

  // ---------- keyboard movement of items ----------
  function moveWithKeys(e, id) {
    const step = e.shiftKey ? 80 : 16;
    const d = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[e.key];
    if (!d) return;
    e.preventDefault();
    const p = positions.get(id);
    positions.set(id, { x: clampPos(p.x + d[0]), y: clampPos(p.y + d[1]) });
    placeItem(id);
    saveSoon();
  }

  // ---------- gestures ----------
  const isEditable = (el) =>
    el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT|BUTTON|A)$/.test(el.tagName));

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
        viewport.classList.add("panning");
        if (background) viewport.focus({ preventScroll: true });
        return;
      }
      const handle = e.target.closest && e.target.closest(".item-handle");
      if (e.button === 0 && handle) {
        const id = handle.closest(".item").dataset.id;
        const p = positions.get(id);
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

  function endGesture(e) {
    if (!gesture || (e && e.pointerId !== undefined && e.pointerId !== gesture.pointerId)) return;
    if (gesture.moved) {
      swallowClick = true; // a pan or drag must not also copy a label or follow a link
      setTimeout(() => (swallowClick = false), 0);
    }
    gesture = null;
    viewport.classList.remove("panning");
    saveSoon();
  }
  window.addEventListener("pointerup", endGesture);
  window.addEventListener("pointercancel", endGesture);
  viewport.addEventListener("lostpointercapture", endGesture);
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
    if (e.target !== viewport || isEditable(e.target)) return;
    const pan = 80;
    const actions = {
      "+": () => zoomCenter(1.2),
      "=": () => zoomCenter(1.2),
      "-": () => zoomCenter(1 / 1.2),
      0: resetCamera,
      1: fitAll,
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

  document.getElementById("zoom-in").addEventListener("click", () => zoomCenter(1.2));
  document.getElementById("zoom-out").addEventListener("click", () => zoomCenter(1 / 1.2));
  document.getElementById("fit").addEventListener("click", fitAll);
  document.getElementById("reset").addEventListener("click", resetCamera);

  // Reveal an offscreen focused item through the camera instead of native scrolling.
  world.addEventListener("focusin", (e) => {
    const el = e.target.closest(".item");
    if (!el) return;
    const p = positions.get(el.dataset.id);
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

  // ---------- live refresh when source changes ----------
  let version = null;
  async function poll() {
    try {
      const res = await fetch("/version", { cache: "no-store" });
      const { v } = await res.json();
      if (version !== null && v !== version) {
        applyRegistry(await loadRegistry(), null);
        await Promise.all(items.map(renderPreview));
        scheduleFrame();
        announce.textContent = "Aperçus mis à jour";
      }
      version = v;
    } catch {
      /* server restarting: try again on the next tick */
    }
  }

  // ---------- start ----------
  async function start() {
    const saved = loadLayout();
    if (saved && saved.camera && finite(saved.camera.x) && finite(saved.camera.y) && finite(saved.camera.z)) {
      camera.x = saved.camera.x;
      camera.y = saved.camera.y;
      camera.z = clampZ(saved.camera.z);
    }
    try {
      applyRegistry(await loadRegistry(), saved);
    } catch (err) {
      announce.textContent = `Registre indisponible : ${err.message}`;
      return;
    }
    scheduleFrame();
    await Promise.all(items.map(renderPreview));
    if (!saved) requestAnimationFrame(fitAll);
    poll();
    setInterval(poll, 1500);
  }
  start();
})();
