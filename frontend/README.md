# Web Dashboard frontend

React + TypeScript + Vite dashboard for the Autonomous AI Career Agent
(Phase 55, [ADR-0073](../docs/adr/0073-react-dashboard-frontend.md)),
consuming the read-only FastAPI backend from Phase 54
([ADR-0072](../docs/adr/0072-web-dashboard-read-api.md)).

See the repository root [`README.md`](../README.md#web-dashboard-frontend-frontend)
for setup, development, and build instructions.

Quick reference:

```bash
npm install
npm run dev      # dev server, proxies /api to career-agent serve (port 8000)
npm run build    # production build -> dist/
npm test         # Vitest + React Testing Library
npx tsc -b       # type-check
npm run lint     # oxlint
```
