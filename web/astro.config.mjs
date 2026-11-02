// @ts-check
import { defineConfig } from "astro/config";
import tailwindcss from "@tailwindcss/vite";

/** The design canvas is a working tool: it exists under `astro dev` only, never in the built site. */
const designCanvas = {
  name: "kaye-design-canvas",
  hooks: {
    /** @param {{ command: string, injectRoute: (route: { pattern: string, entrypoint: string }) => void }} options */
    "astro:config:setup": ({ command, injectRoute }) => {
      if (command === "dev") injectRoute({ pattern: "/canvas", entrypoint: "./src/canvas/CanvasPage.astro" });
    },
  },
};

export default defineConfig({
  site: "https://kaye.vercel.app",
  integrations: [designCanvas],
  i18n: {
    locales: ["fr", "en"],
    defaultLocale: "fr",
    routing: { prefixDefaultLocale: false },
  },
  vite: { plugins: [tailwindcss()] },
});
