import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import tailwindcss from "@tailwindcss/vite";

// The threaded OpenMS module needs a cross-origin isolated page. serve.py
// sends the same headers for the built app.
const isolation = {
  "Cross-Origin-Opener-Policy": "same-origin",
  "Cross-Origin-Embedder-Policy": "require-corp",
};

export default defineConfig({
  // relative, so the build works from any folder of any static server
  base: "./",
  plugins: [tailwindcss(), svelte()],
  // settings.json, docs/ and example-data/ are read from the repository root
  server: { headers: isolation, fs: { allow: [".."] } },
  preview: { headers: isolation },
  worker: { format: "es" },
  build: { chunkSizeWarningLimit: 5000, target: "es2022", assetsInlineLimit: 0 },
});
