import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      // career-agent serve (Phase 54, ADR-0072) defaults to 127.0.0.1:8000.
      "/api": "http://127.0.0.1:8000",
    },
  },
});
