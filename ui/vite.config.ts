import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Local-only dev server. The React app calls /api/*, which we proxy to the
// stdlib Python API (ui/server.py) on :8770 so both run on one origin in dev.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: false,
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
