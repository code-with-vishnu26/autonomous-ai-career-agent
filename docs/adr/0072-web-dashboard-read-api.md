# ADR-0072: Web Dashboard — read-only FastAPI layer over the existing service layer

- **Status:** Accepted
- **Date:** 2026-07-11
- **References:** [ADR-0068](0068-resume-variant-engine.md)/[ADR-0069](0069-application-preparation-engine.md)/[ADR-0070](0070-human-review-center.md)/[ADR-0071](0071-human-approved-submission-engine.md)
  (the four stores this phase reads from — `SqliteResumeVariantStore`/
  `SqliteApplicationSessionStore`/`SqliteReviewSessionStore`/
  `SqliteSubmissionResultStore` — all consumed unmodified),
  [ADR-0050](0050-execution-safety-boundary.md) (the fail-closed submission
  boundary this phase does not touch, and deliberately cannot reach)

## Context

The backend core workflow (Search → Plan → Discover → Tailor → Prepare →
Review → Approve → Submit → Track → Export) is complete and CLI-driven
(Phases 1-53). The user's brief for this phase asked for a web dashboard: a
FastAPI backend plus a React/TypeScript frontend, explicit that the API
"must reuse the existing Python service layer" and must not duplicate CLI
logic.

That brief is large — a new frontend toolchain and a new backend layer in
one pass, on top of a codebase that has never had either. Rather than build
both at once with no intermediate checkpoint, this phase scopes down to the
backend API surface only, and further scopes that surface to **read-only**:
every dashboard page the brief describes (Dashboard, Applications, Review
Queue, Submission Queue, History, Analytics, Settings) needs to *display*
data the CLI already produces before it needs to *trigger* anything. The
one page with a real write action in the brief — Search Jobs (triggering
discovery) — and any action that would let the dashboard approve a review
or trigger a submission, are excluded from this phase entirely: submission
in particular is the single most safety-critical boundary in this codebase
(ADR-0050/0071), and extending it to a second entry point (an HTTP request
instead of a supervised terminal session) is not a decision to make as a
side effect of shipping a dashboard's data layer.

The React frontend that consumes this API is the immediate follow-up phase,
not part of this one — this ADR covers the backend slice only.

## Decision

### One store, one router, no new logic

`src/career_agent/api/` is a thin FastAPI layer. Each router
(`applications.py`, `reviews.py`, `submissions.py`, `resume_variants.py`)
wraps exactly one existing store class and calls exactly one existing
method on it (`all_sessions()`, `all_reviews()`, `all_results()`,
`all_variants()`). `analytics.py` adds one aggregation step
(`collections.Counter` over the status field each store already returns) —
not a new metrics engine, and deliberately does not touch the older
`SqliteApplicationStore`/funnel-report pipeline (`career-agent report`),
which Phases 51-53's ADRs already documented as a separate, parallel
pipeline; conflating the two here would misrepresent one pipeline's data as
the other's.

`api/dependencies.py` constructs each store from `Settings.database_path`,
the same composition-root pattern `cli.py` uses per command — `Settings()`
is read fresh on every call (no caching), so the API stays sensitive to an
env change without a restart and safe to test with per-test
`monkeypatch.setenv`.

### Read-only is enforced structurally, not just by convention

`CORSMiddleware` is configured with `allow_methods=["GET"]`, and every
router only registers `@router.get(...)` handlers — there is no `@router
.post`/`put`/`delete` anywhere in this package. A dedicated test
(`test_only_get_methods_are_registered`) enumerates every route FastAPI
actually registered on the built app and asserts each one's allowed
methods are a subset of `{GET, HEAD, OPTIONS}`. This is what actually
guarantees "no discover/prepare/review-approve/submit trigger reachable
from the API" for this phase — a docstring claim alone would rot the
moment someone added a route without reading it.

### Settings redaction

`GET /api/settings` returns every `Settings` field except a fixed
`_SECRET_FIELDS` set (API keys, tokens, chat IDs) — those fields are
reported only as `configured_secrets: {field: bool}`, never their values.
This mirrors the existing `test_env_example_has_no_real_secrets.py`
discipline of never letting a secret reach an output surface.

### `career-agent serve`

A new CLI subcommand, `career-agent serve [--host] [--port]`, runs
`uvicorn.run(create_app(), ...)`. `fastapi`/`uvicorn` are imported lazily
inside `run_serve_command`, and added as a new optional extra
(`pip install 'career-agent[web]'`) rather than a hard runtime dependency —
every other command continues to work with a plain install, matching how
LLM providers are already imported lazily per-command. Running without the
extra installed prints a clear message and returns exit code 1 rather than
an import traceback.

### What this phase explicitly does not do

- No route can trigger discovery, tailoring, review approval, or
  submission. Those remain exclusively `career-agent discover`/`prepare`/
  `review`/`submit` CLI actions. In particular, `SubmissionEngine`
  (ADR-0071) is not imported anywhere under `career_agent.api`.
- No React frontend. This ADR covers the backend read API only; the
  frontend is the next phase.
- No authentication. This is a single-user, self-hosted, localhost-only
  tool (the README's own framing); `career-agent serve` defaults to
  `127.0.0.1`, and CORS only allows the local Vite dev server origins.
  Multi-user auth is explicitly a future phase (Phase 55+), not a gap in
  this one — there is nothing to authenticate against yet.
- No new database schema, no new domain model. Every response is one of
  the existing Pydantic models (`ApplicationSession`, `ReviewSession`,
  `SubmissionResult`, `ResumeVariant`) serialized as-is by FastAPI, or a
  small locally-defined aggregate (`AnalyticsSummary`, `RedactedSettings`)
  built from them.

## Consequences

- 15 new tests (`tests/api/test_dashboard_api.py`,
  `tests/test_cli_serve.py`), all passing alongside the existing suite.
- The dashboard's data layer is provable end-to-end today via `curl`/the
  FastAPI-generated OpenAPI docs, without waiting on the frontend.
- The next phase (the React frontend) has a stable, already-tested API
  contract to build against, and can be scoped and reviewed independently
  of backend risk.
- Write-capable dashboard actions (starting a search, approving a review,
  triggering a submission from the browser instead of a terminal) remain
  open questions for a later phase, each deserving its own explicit
  safety review — most importantly whether `career-agent submit`'s
  countdown/confirmation gate can be faithfully reproduced over HTTP at
  all, given it currently blocks on a real terminal `input()` call.

## Revisit criteria

- If the frontend phase finds the read-only surface insufficient (e.g. it
  needs a "trigger discover" button), that is a new, explicitly-scoped
  decision — not an extension to slip into a UI-only phase.
- If a second frontend consumer ever needs write access, revisit whether
  submission-over-HTTP is safe at all before adding it, rather than
  defaulting to "the CLI already gates it, so the API can too."
