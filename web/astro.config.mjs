// @ts-check
import { defineConfig } from "astro/config";
import tailwindcss from "@tailwindcss/vite";

/** The design canvas and the share-card source are working tools: they exist under `astro dev`
 * only, never in the built site. `/og` is captured once into public/og.png (see OgCard.astro). */
const designCanvas = {
  name: "kaye-design-canvas",
  hooks: {
    /** @param {{ command: string, injectRoute: (route: { pattern: string, entrypoint: string }) => void }} options */
    "astro:config:setup": ({ command, injectRoute }) => {
      if (command !== "dev") return;
      injectRoute({ pattern: "/canvas", entrypoint: "./src/canvas/CanvasPage.astro" });
      injectRoute({ pattern: "/og", entrypoint: "./src/canvas/OgCard.astro" });
    },
  },
};

export default defineConfig({
  site: "https://kaye-app.vercel.app", // kaye.vercel.app belongs to another Vercel account
  integrations: [designCanvas],
  devToolbar: { enabled: false },
  i18n: {
    locales: ["fr", "en"],
    defaultLocale: "fr",
    routing: { prefixDefaultLocale: false },
  },
  vite: { plugins: [tailwindcss()] },
});
