# Environment Variables (Phase 59, ADR-0076)

Three tracked template files, layered for different purposes -- see each
one's own header comment for exactly when to use it:

| File | Purpose | Safe to commit? |
|---|---|---|
| `.env.example` | Local, non-Docker development (`career-agent serve` / CLI commands directly) | Yes (placeholders only) |
| `docker.env` | Default `docker compose up` values | Yes (placeholders only) |
| `production.env.example` | Template for a real production deployment | Yes (placeholders only) |

Copy whichever applies to `.env` / `production.env` and fill in real
values -- **never commit the filled-in file**; all three real variants
(`.env`, `production.env`) are gitignored.

## Required

| Variable | Required when | Notes |
|---|---|---|
| `JWT_SECRET_KEY` | Always, to use the dashboard API at all | No default -- the API fails closed (`500`) on any auth route, and `validate_startup` reports this as an **error** (refuses-to-be-considered-ready signal, logged at startup) when `ENVIRONMENT=production`. Generate: `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `GROQ_API_KEY` or `ANTHROPIC_API_KEY` | To use tailoring, the truthfulness gate, or any Career Coach AI feature | At least one; Groq is tried first (free tier) everywhere in this project. Deterministic features (Resume Analysis, Job Match, Skill Gap, the read-only dashboard) work without either |

## Optional -- deployment / infrastructure (Phase 59)

| Variable | Default | Notes |
|---|---|---|
| `ENVIRONMENT` | `development` | `development` \| `testing` \| `production`. Affects only `validate_startup`'s strictness and default log format -- never a business rule |
| `JSON_LOGS` | on in production, off otherwise | Force either way regardless of `ENVIRONMENT` |
| `LOG_LEVEL` | `INFO` | Standard Python logging level name |
| `JWT_COOKIE_SECURE` | `false` | Set `true` once served over real HTTPS -- see `production.md` |
| `DATABASE_URL` | unset | Accepted, validated, **not yet consumed** -- see `production.md`'s database section and ADR-0076 |
| `POSTGRES_DB`/`POSTGRES_USER`/`POSTGRES_PASSWORD` | `career_agent`/`career_agent`/`career_agent` | Only used if you start the `postgres` Compose profile; the running Postgres container itself, not the application |

## Optional -- existing application config (Phases 1-57, unchanged)

Every variable `.env.example` already documents is unaffected by this
phase -- `DATABASE_PATH`, `ARTIFACTS_DIR`, `BROWSER_SESSION_DIR`,
`PROMPTFOO_RESULTS_DIR`, `CLI_LOCAL_USER_EMAIL`, the discovery-source keys
(`ADZUNA_*`, `REED_API_KEY`, `USAJOBS_*`, `JOOBLE_API_KEY`), notification
keys (`TELEGRAM_*`, `NTFY_TOPIC`), and search-provider keys (`EXA_API_KEY`,
`GOOGLE_CSE_*`). See `.env.example` itself for the authoritative,
in-sync list -- not duplicated here to avoid the two drifting apart.

## Missing-variable warnings

`career-agent serve` (and the FastAPI app's own startup, when run via
Docker) logs every finding from `core/startup_validation.py::validate_startup`
at process start:

- **Errors** (only possible in `ENVIRONMENT=production`): missing
  `JWT_SECRET_KEY`. The process still starts (the existing per-request
  fail-closed check is the real enforcement -- this only surfaces the
  same fact earlier, in the log stream, before the first request hits it).
- **Warnings** (any environment): missing LLM provider key,
  `DATABASE_URL` set but not consumed, `JWT_COOKIE_SECURE` off in
  production.

Check `docker compose logs backend | head -20` after a fresh start to see
these.
