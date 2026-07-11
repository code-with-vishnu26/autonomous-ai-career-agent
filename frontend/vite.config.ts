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
      // career-agent serve (Phase 54/56, ADR-0072/0074) defaults to
      // 127.0.0.1:8000. /auth and /user carry the refresh cookie, so this
      // proxy is also why the dev server and the API can share cookies
      // as if same-origin despite running on different ports.
      "/api": "http://127.0.0.1:8000",
      "/auth": "http://127.0.0.1:8000",
      "/user": "http://127.0.0.1:8000",
    },
  },
});
