import { defineConfig } from "vitest/config";

// The engine, the workflow framework and the example workflow run in Node on
// the same OpenMS WebAssembly module as in the browser.
export default defineConfig({
  test: { environment: "node", include: ["tests/**/*.test.ts"], testTimeout: 300_000, hookTimeout: 300_000 },
});
