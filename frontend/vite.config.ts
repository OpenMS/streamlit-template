import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import tailwindcss from "@tailwindcss/vite";

// `npm run dev` serves the app on :5173 and forwards /api to the local
// server started with `python -m server --no-browser` (port 8765).
export default defineConfig({
  plugins: [tailwindcss(), svelte()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/assets/openms-logo.svg": "http://127.0.0.1:8765",
      "/insight-component": "http://127.0.0.1:8765",
    },
  },
  build: { chunkSizeWarningLimit: 5000 },
});
