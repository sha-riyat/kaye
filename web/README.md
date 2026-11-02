# kaye.vercel.app

The Kayé website: Astro 7 and Tailwind CSS 4, built to a static page with almost no JavaScript,
so it opens fast on a small Android phone on 3G.

```bash
npm install
npm run dev        # http://localhost:4321, and the design canvas at /canvas
npm run build      # dist/, what Vercel serves (the canvas is not in it)
npx astro check    # types
```

- `src/styles/global.css`: the brand book as Tailwind tokens (Nuit, Cauri, Solaire, Latérite, Lagune,
  Bricolage Grotesque, Inter) and the motion vocabulary (rise, pop, draw, reveal, breathe).
- `src/components/`: the page's building blocks. `ChatDemo` plays a conversation with Kayé by itself,
  `RegisterPage` reads a handwritten page line by line; both run only while on screen and stand still
  under reduced motion.
- `src/canvas/`: the design canvas (`astro dev` only). `registry.ts` lists every variant with a stable
  id, a readable name and its size; each frame is its own size container, so the same component shows
  its desktop and phone layouts side by side.
- `src/assets/photos/`: photos from Pexels and Unsplash under their free licences, already passed
  through the Solaire filter of the brand book. `src/assets/tickets/`: real renders of the app's
  documents (`uv run python -m scripts.web_tickets` from the repository root).
