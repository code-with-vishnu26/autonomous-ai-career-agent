import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";
import type { IncomingMessage } from "node:http";

// career-agent serve (Phase 54/56, ADR-0072/0074) defaults to 127.0.0.1:8000.
// Every server prefix the dashboard calls needs a proxy entry, including the
// write-capable routers that live OFF the /api prefix by design since Phase 63
// (discover/prepare/reviews/submissions) and the binary /export download
// (ADR-0081/0083/0085/0086) -- otherwise those calls 404 against the dev
// server instead of reaching the API.
//
// Several of these prefixes (/coach, /notifications, /notification-settings,
// /organizations) are ALSO client-side React Router routes. A naive proxy
// forwards a browser *navigation* (or refresh/bookmark) to those URLs to the
// backend, which returns raw JSON ("Method Not Allowed") instead of the app.
// The `bypass` below fixes that: a document request (Accept: text/html) is
// served the SPA so React Router handles the route, while an API request
// (fetch/XHR, Accept: application/json or a blob download) is proxied to the
// backend. This makes deep links + refresh work on every page.
const API_PREFIXES = [
  "/api",
  "/auth",
  "/user",
  "/coach",
  "/discover",
  "/prepare",
  "/reviews",
  "/submissions",
  "/export",
  "/organizations",
  "/team",
  "/billing",
  "/notifications",
  "/notification-settings",
];

function apiProxy() {
  const bypass = (req: IncomingMessage): string | undefined =>
    req.method === "GET" && (req.headers.accept ?? "").includes("text/html")
      ? "/index.html"
      : undefined;
  return Object.fromEntries(
    API_PREFIXES.map((prefix) => [
      prefix,
      { target: "http://127.0.0.1:8000", changeOrigin: true, bypass },
    ]),
  );
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: apiProxy(),
  },
});
