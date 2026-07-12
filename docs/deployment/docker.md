# Docker (Phase 59, ADR-0076)

## Prerequisites

- Docker Engine 24+ with the Compose v2 plugin (`docker compose version`
  should print a v2 line, not the old standalone `docker-compose`).
- No API keys are required just to start the stack -- health/readiness
  work without them. Tailoring, the truthfulness gate, and the Career
  Coach's AI features need `GROQ_API_KEY` or `ANTHROPIC_API_KEY` (see
  `environment.md`).

## Quick start (local, SQLite)

```bash
git clone https://github.com/code-with-vishnu26/autonomous-ai-career-agent.git
cd autonomous-ai-career-agent
docker compose up --build
```

This builds and starts three containers -- `backend` (FastAPI + gunicorn),
`frontend` (the built React app served by nginx), and `nginx` (the edge
reverse proxy) -- using `docker.env`'s tracked, safe-default values.
Visit `http://localhost` once `docker compose ps` shows `backend` and
`frontend` as healthy.

To use your own values (an LLM key, a real `JWT_SECRET_KEY`, ...), copy
`docker.env` to `.env` and edit it, then run:

```bash
docker compose --env-file .env up --build
```

## What's in the base stack

| Container | Image | Role |
|---|---|---|
| `backend` | built from `Dockerfile.backend` | FastAPI dashboard API (gunicorn + uvicorn workers), SQLite by default |
| `frontend` | built from `Dockerfile.frontend` | Static React build served by nginx |
| `nginx` | built from `deploy/nginx/Dockerfile` | Edge reverse proxy: `/`→frontend, `/api`,`/auth`,`/user`,`/coach`,`/health`,`/ready`,`/metrics`→backend |
| `postgres` | `postgres:16-alpine` (profile `postgres`) | Not consumed by the app yet -- see `production.md` |
| `redis` | `redis:7-alpine` (profile `redis`) | Not consumed by the app yet -- see `production.md` |

`postgres`/`redis` don't start with a plain `docker compose up` -- they're
gated behind Compose profiles:

```bash
docker compose --profile postgres --profile redis up --build
```

## Development (hot reload)

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

This overlay replaces the production backend command with
`uvicorn --reload` (source mounted from `./src`), replaces the frontend
container with a Vite dev server on `http://localhost:5173` (source
mounted from `./frontend/src`), and disables the edge `nginx` container
(Vite's own dev-server proxy, `frontend/vite.config.ts`, already forwards
`/api`, `/auth`, `/user`, `/coach` to the backend -- the same list the edge
proxy config uses, one source of truth).

Not using Docker at all for local development remains fully supported and
is unaffected by any of this -- `career-agent serve` +
`cd frontend && npm run dev` (README's existing instructions) still works
exactly as before.

## Production

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  --env-file production.env up -d --build
```

See `production.md` for the full walkthrough (TLS, resource limits,
`JWT_COOKIE_SECURE`, restart policies).

## Rebuilding after a code change

```bash
docker compose build backend   # or: frontend, nginx
docker compose up -d
```

## Logs

```bash
docker compose logs -f backend
docker compose logs -f          # every container
```

JSON-formatted by default in production (`JSON_LOGS=true` in
`docker.env`/`production.env.example`) -- see `monitoring.md`.

## Data persistence

The SQLite database, generated artifacts, browser session state, and
promptfoo results all live in the `career_agent_data`/
`career_agent_promptfoo` named volumes (declared in `docker-compose.yml`),
not inside the container filesystem -- `docker compose down` (without
`-v`) leaves them intact; `docker compose down -v` deletes them.

```bash
docker volume ls | grep career_agent
docker compose down       # containers removed, data volumes kept
docker compose down -v    # containers AND data volumes removed
```

## Browser automation inside Docker

`Dockerfile.backend`'s builder stage runs
`playwright install --with-deps chromium` -- the exact same Chromium this
project already depends on (`pyproject.toml`'s `playwright>=1.44`), not a
new browser. The final runtime stage separately apt-installs Chromium's
shared-library dependencies (fonts, X11/GTK libs) since Docker's
multi-stage build doesn't carry the builder stage's apt cache across.
`PLAYWRIGHT_BROWSERS_PATH` is set to `/app/.cache/ms-playwright` so the
copied browser cache is found at runtime.

The Submission Engine (ADR-0071) and Browser Automation Foundation
(ADR-0065) are **completely unchanged** by this phase -- containerizing
Chromium doesn't touch `BrowserManager`, `SessionManager`, `TabManager`,
`BrowserApplicator`, or `SubmissionEngine`'s fail-closed gate in any way.

**A real, named gap, not silently worked around**: `BrowserManager.launch`
defaults to `headless=False` deliberately (`integrations/browser/
browser_manager.py`'s own docstring: "a human must be able to see and
interact with the browser" for the human-in-the-loop review/confirmation
this project's whole safety model depends on -- ADR-0069/0070/0071), and
no CLI flag currently overrides it. A headed Chromium needs a real
display; the backend container as shipped here has none, so
`career-agent prepare`/`submit` are **not** expected to work inside the
`backend` container out of the box. This phase deliberately did not add a
`--headless` flag or an X11/VNC setup to force one -- doing either would
be a real change to the Submission Engine's human-in-the-loop safety
posture, explicitly out of scope ("Do not alter Submission Engine," this
phase's own brief).

Playwright's Chromium + its apt dependencies are verified *actually
launching* (headless, inside the built backend image) as a real CI step,
not merely present -- see `.github/workflows/ci.yml`'s `docker` job. That
proves the dependency; it is not the same claim as "browser automation
runs inside this container," which it does not, for the headed-by-design
reason above. Running `prepare`/`review`/`submit` for real remains a CLI
workflow on a machine with a real display, exactly as documented in the
main README today.

## Troubleshooting

See `docs/deployment/production.md#troubleshooting` for the full list;
the two most common local issues:

- **`backend` never becomes healthy**: run `docker compose logs backend`.
  A missing `JWT_SECRET_KEY` does not block startup (only auth endpoints
  fail closed at request time) -- `/health`/`/ready` still report ok.
  Check the database volume is writable.
- **Chromium fails to launch inside the container**: confirm the image
  actually built the `runtime` stage's apt packages (rebuild with
  `--no-cache` if you suspect a stale layer) and that
  `PLAYWRIGHT_BROWSERS_PATH` matches where the builder stage installed
  Chromium (`/app/.cache/ms-playwright`).
