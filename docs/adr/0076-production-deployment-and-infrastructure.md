# ADR-0076: Production Deployment & Infrastructure

- **Status:** Accepted
- **Date:** 2026-07-13
- **References:** [ADR-0072](0072-web-dashboard-read-api.md)/[ADR-0073](0073-react-dashboard-frontend.md)
  (the backend/frontend this phase containerizes, unchanged), [ADR-0074](0074-authentication-and-multi-user-platform.md)
  (`JWT_COOKIE_SECURE`'s own docstring already named "Phase 59" as when a
  real HTTPS deployment should set it true), [ADR-0065](0065-browser-automation-foundation.md)/[ADR-0071](0071-human-approved-submission-engine.md)
  (Browser Automation Foundation / Submission Engine, both explicitly
  unchanged by this phase)

## Context

The application is functionally complete through Phase 57 (AI Career
Coach) but has no supported path to running anywhere other than a
developer's own machine with Python/Node installed directly. The user's
brief asks for a production-ready Docker deployment: multi-stage builds,
an nginx reverse proxy with HTTPS readiness, health/readiness/metrics
endpoints, structured logging, PostgreSQL support alongside SQLite, and
CI coverage for the Docker build itself -- explicitly scoped down by its
own stated constraints: reuse existing architecture, do not duplicate
logic, do not rewrite backend services, do not touch the Submission
Engine or Authentication.

**A repository-reality audit found a genuine conflict inside the brief
itself.** `storage/sqlite.py` is ~15 store classes built directly on the
standard library's `sqlite3` module, with hand-written SQL and `?`
placeholders -- there is no database-abstraction layer underneath any of
them. Building real PostgreSQL support means one of two things: duplicate
every store for a second backend, or migrate the whole storage layer onto
something like SQLAlchemy. Both directly contradict the brief's own "do
not duplicate logic" / "do not rewrite backend services" instructions.
This was surfaced to the user as an explicit scoping question (the same
discipline Phase 57's audit used for its own four deferred features)
rather than either quietly faking `DATABASE_URL` support or unilaterally
undertaking a multi-day storage-layer rewrite. **The user chose: ship the
Docker/Nginx/health/logging infrastructure for real; `DATABASE_URL` is
accepted and validated in configuration, and a `postgres` Compose service
is included, but the storage layer stays SQLite-only, named as a
deferred follow-up, not built.**

## Decision

### Docker: two application images, one edge proxy, all non-root

`Dockerfile.backend` is a two-stage build: the builder stage installs the
package (`pip install ".[web]"`) and runs
`playwright install --with-deps chromium` -- the exact Chromium this
project already depends on (`pyproject.toml`'s `playwright>=1.44`), not a
new one; the runtime stage re-installs only Chromium's shared-library
apt dependencies (multi-stage builds don't carry the builder's apt cache
across), copies the installed `site-packages` + browser cache, and runs
as a non-root `career-agent` user via gunicorn supervising 4 uvicorn
workers. `Dockerfile.frontend` builds the exact same `npm ci && npm run
build` CI already runs (ADR-0073's `verify-frontend` job), then serves
the static output through nginx, non-root, with a custom main
`nginx.conf` (no `user` directive -- there's no root process to drop
privileges from when the container itself already runs non-root).
`deploy/nginx/` holds a third, small image: the edge reverse proxy,
non-root the same way, routing `/` to the frontend container and
`/api`, `/auth`, `/user`, `/coach`, `/health`, `/ready`, `/metrics` to the
backend container -- the exact same path list
`frontend/vite.config.ts`'s dev-server proxy already uses, one source of
truth for "which paths are backend paths," not reinvented per layer.

### Health/readiness/metrics: extending, not replacing, Phase 54's `/api/health`

`/api/health` (Phase 54) is unchanged -- the frontend already calls it.
Three new top-level routes (no `/api` prefix, matching container-
orchestrator convention: a health check probes a fixed path, not one
nested under an app-specific prefix) live in the same
`api/routers/health.py`: `/health` (liveness -- process is up, nothing
else), `/ready` (readiness -- opens the SQLite database at
`DATABASE_PATH`, the same connection every real store already makes;
returns `503`, never a falsely-green `200`, the instant that fails), and
`/metrics` (Prometheus text-exposition format: process uptime + request
counts by status class, via a small hand-formatted function -- no
`prometheus_client` dependency, since a fixed set of counters is all the
brief's "Optional Prometheus metrics" actually asks for). All three
routes are GET-only, so they need no change to the existing `/api/*`-is-
GET-only / `/auth/`,`/user/`,`/coach/`-are-the-only-write-capable-routers
structural tests (ADR-0072/0074/0075).

### Structured logging: a stdlib formatter, not a new dependency

`core/logging_config.py::JsonFormatter` is one small
`logging.Formatter` subclass emitting one JSON object per line -- the
format every container log collector already parses -- rather than
adopting `structlog`/`python-json-logger` for what one class already
does. On by default in `ENVIRONMENT=production`, overridable either way
via `JSON_LOGS`. `api/middleware.py::log_requests` logs one line per
request (method/path/status/duration) and **never logs headers or the
request/response body** -- those can carry an access token, a refresh
cookie, or an LLM API key, the same care Phase 56/57 already took not to
leak a secret into a log or error message.

### Startup validation: surfaces the same fail-closed facts earlier, changes no enforcement

`core/startup_validation.py::validate_startup` returns a
`StartupReport` (errors/warnings as data, not raised exceptions or
printed text) so both `career-agent serve`'s own entrypoint and the
FastAPI app's `lifespan` startup hook can present the same findings
through their own channel -- the "check the evidence" discipline
`llm/promptfoo_gate.py::verify_promptfoo_results` already established for
a different kind of unverified assertion, applied here to configuration.
A missing `JWT_SECRET_KEY` is an **error** only when
`ENVIRONMENT=production` (elsewhere a warning) -- but this function never
refuses to start the process either way; the actual enforcement remains
exactly what it already was, `api/security.py::require_jwt_secret`
failing closed per-request. This only makes the same fact visible in the
log stream before the first request arrives, which is what a container
orchestrator's log-based alerting needs.

### `DATABASE_URL`: accepted, validated, explicitly not consumed

`Settings.database_url` exists so the configuration surface the brief
asked for is present and the intent is honestly recorded -- setting it
produces a startup warning ("not yet consumed... `DATABASE_PATH` is what
actually determines where data is written"), never a silent no-op an
operator could mistake for working. The `postgres` Compose service
(profile-gated, off by default) exists for the same reason: present and
startable, not pretending to be wired in. See `docs/deployment/
production.md`'s database section and the Future Revisit Criteria below
for what a real migration would actually require.

### `redis`: present, also not consumed

There is no caching layer anywhere in this codebase to back with Redis --
adding one speculatively, only so the `redis` container has something to
do, would be exactly the kind of unrequested abstraction this project's
own discipline avoids. The `redis` Compose service is profile-gated
(`--profile redis`) for the same "infrastructure shape present, not
faked" reasoning as `postgres`.

### CI: a fourth job, Linux-only, doing real work

`.github/workflows/ci.yml` gains a `docker` job (ubuntu-latest only --
the existing backend `verify` job's Windows/macOS scope decision,
ADR-0056, already draws this same Linux-only line for anything Docker-
shaped): validates all three Compose files
(`docker compose ... config --quiet`), builds all three images for real,
**verifies Playwright's Chromium actually launches** inside the built
backend image (headless, a real `sync_playwright().chromium.launch()`
call, not an assumption -- the brief explicitly asks for this), starts
the full stack, waits for `/ready`, and smoke-tests `/health`,
`/metrics`, and the frontend's root HTML through the edge proxy before
tearing everything down.

### Browser automation: unchanged, and headed-by-design -- a named, not silently patched, container gap

`BrowserManager.launch` defaults to `headless=False` deliberately (its
own docstring: "a human must be able to see and interact with the
browser," matching the human-in-the-loop review/confirmation the whole
Submission Engine safety model depends on, ADR-0069/0070/0071), and no
CLI flag overrides it. The `backend` container as shipped has no display
server, so `career-agent prepare`/`review`/`submit` are not expected to
work inside it out of the box. Adding a `--headless` override or an X11/
VNC setup to force headed automation to work in a container would be a
real change to the Submission Engine's safety posture -- explicitly out
of scope ("Do not alter Submission Engine," this phase's own brief).
Named honestly in `docs/deployment/docker.md`, not silently worked
around; the CI job's headless Chromium-launch check proves the
*dependency* is present and functional, not that the full
`prepare`/`submit` CLI workflow runs inside this container.

## What this phase explicitly does not do

- **No real PostgreSQL support.** Accepted-and-validated configuration
  only, per the user's confirmed scoping decision above. Would require a
  real storage-layer redesign (SQLAlchemy or an equivalent abstraction
  layer), explicitly out of scope for an infrastructure phase.
- **No Redis-backed caching or rate limiting.** There is nothing in this
  codebase for Redis to cache; Phase 56's rate limiter remains the
  documented in-memory, single-process implementation it already was
  (ADR-0074 already named Redis as future work for a multi-instance
  deployment, unchanged by this phase).
- **No Kubernetes/orchestrator manifests.** Single-host Docker Compose
  only, matching the brief's own "anywhere using Docker" framing, not a
  cluster-orchestration commitment.
- **No automatic TLS certificate provisioning.** A real certificate must
  be obtained and mounted manually (`docs/deployment/production.md`);
  generating a self-signed one automatically would be a false "it's
  secured" signal.
- **No browser automation inside the container.** Named above -- the
  Submission Engine's headed-by-design safety posture is unchanged, and
  making it work headlessly inside Docker is a distinct, separate design
  question this phase does not decide.
- **No zero-downtime/rolling deploys.** A `docker compose up -d --build`
  restart has a brief downtime window; out of scope for a single-host
  Compose deployment.

## Consequences

- Backend: `core/logging_config.py`, `core/startup_validation.py`,
  `api/middleware.py`, `api/routers/health.py` extended (`/health`,
  `/ready`, `/metrics`, alongside the unchanged `/api/health`),
  `api/app.py`'s `lifespan` hook wires both. `Settings` gains
  `environment`, `database_url`, `json_logs`. `gunicorn` added to the
  `web` extra (Linux/macOS only -- no Windows fork support).
  `frontend/src/services/http.ts` gains a build-time `VITE_API_BASE_URL`
  prefix (empty by default -- every existing relative-path call is
  unaffected; only meaningful when backend and frontend are genuinely
  served from different origins). 30 new backend tests, 1 new frontend
  test; full suites, ruff, lint-imports, `tsc`/`oxlint`/`vite build`
  green.
- Infrastructure: `Dockerfile.backend`, `Dockerfile.frontend`,
  `Dockerfile.frontend.dev`, `deploy/nginx/` (edge proxy image + configs
  + a documented, unwired TLS example), `docker-compose.yml`/`.dev.yml`/
  `.prod.yml`, `.dockerignore`, `docker.env`, `production.env.example`.
  `.github/workflows/ci.yml` gains a `docker` job doing a real build +
  Compose validation + Playwright-launch verification + container-
  startup smoke test.
- Documentation: `docs/deployment/{docker,production,environment,
  monitoring}.md`; README/ROADMAP updated.
- Zero changes to `SubmissionEngine`, `BrowserApplicator`,
  `BrowserManager`/`SessionManager`/`TabManager`, any auth logic
  (`core/security.py`, `api/routers/auth.py`), or any business rule
  anywhere in `domain/`/`agents/`.

## Future revisit criteria

- If real PostgreSQL support is ever built, it should be a dedicated
  phase of its own -- most plausibly a migration of `storage/sqlite.py`
  onto SQLAlchemy Core (preserving each store's existing method
  signatures so callers don't change), with a real dual-backend test
  matrix, not a bolt-on. Revisit this ADR's deferral reasoning at that
  point, not before.
- If a genuine caching need appears (a slow aggregation, a rate limiter
  that needs to survive a restart or coordinate across multiple backend
  instances), design that against the now-present `redis` Compose
  service explicitly, rather than assuming it already does anything.
- If browser automation inside a container is ever genuinely needed (a
  fully headless, unattended submission flow), that is a safety-model
  change to the Submission Engine requiring its own explicit user
  authorization -- the same standard ADR-0071's original crossing of the
  submit boundary required -- not something to slip in as an
  infrastructure detail.
- If this ever needs more than one host (true horizontal scaling), the
  single-host Compose model and the in-memory rate limiter/metrics
  counter both need a real distributed replacement, not a bigger local
  workaround -- ADR-0074 already named this for the rate limiter.
