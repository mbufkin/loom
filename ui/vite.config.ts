import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const root = path.dirname(fileURLToPath(import.meta.url));

// Local-only dev server. The React app calls /api/*, which we proxy to the
// stdlib Python API (ui/server.py) on :8770 so both run on one origin in dev.
// Pin root explicitly: a config HMR restart once lost the entry HTML and the
// /api proxy silently fell through to the SPA index (HTML for every /api call).
export default defineConfig({
  root,
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8770",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
  },
});
