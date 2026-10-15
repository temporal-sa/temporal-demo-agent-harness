import { svelte } from "@sveltejs/vite-plugin-svelte";
import { defineConfig } from "vite";

// `npm run dev` serves on :5173 and proxies the API and the console to the Python web
// process on :8000. `npm run build` writes the bundle the web process serves at `/`.
export default defineConfig({
  plugins: [svelte()],
  base: "./",
  build: { outDir: "../agent_harness_demo/ui_dist", emptyOutDir: true },
  server: {
    proxy: { "/api": "http://localhost:8000", "/console": "http://localhost:8000" },
  },
});
