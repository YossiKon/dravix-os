import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// During `npm run dev`, proxy API + WebSocket traffic to the Python core
// running on http://localhost:8800. In production the core serves web/dist/
// itself, so requests are same-origin and no proxy is needed.
export default defineConfig({
  // Relative asset paths — the app must work both at http://host:8800/ and under
  // Home Assistant ingress (/api/hassio_ingress/<token>/), where "/assets/..." 404s.
  base: "./",
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8800",
        changeOrigin: true,
      },
      // Robot camera snapshot stream (served same-origin in production).
      "/camera": {
        target: "http://localhost:8800",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://localhost:8800",
        ws: true,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
