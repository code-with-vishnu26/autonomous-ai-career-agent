# ADR-0073: React Dashboard frontend — consumes the read-only API, invents no write path

- **Status:** Accepted
- **Date:** 2026-07-11
- **References:** [ADR-0072](0072-web-dashboard-read-api.md) (the FastAPI
  backend this phase is the frontend for — every data point on every page
  traces to one of its six `GET` routes), [ADR-0070](0070-human-review-center.md)/[ADR-0071](0071-human-approved-submission-engine.md)
  (the human-in-the-loop boundaries this phase deliberately does not
  reproduce over HTTP)

## Context

ADR-0072 explicitly named the frontend as its own immediate follow-up
phase, scoped against "this now-tested API contract." The user's brief for
this phase asks for a full production dashboard — 8 pages, dark mode,
responsive layout, charts — built with React/TypeScript/Vite/Tailwind/
shadcn-ui/TanStack-Query/React-Router/React-Hook-Form/Recharts, calling
"the existing FastAPI endpoints" and explicitly forbidding duplicated
backend/API logic.

The brief's page specs (Search Jobs' "Search" button calling the API;
Review Queue's Approve/Reject buttons; Submission Queue's countdown and
"current browser state") assume write endpoints that do not exist —
ADR-0072 shipped six `GET` routes only, by design. Fabricating client-side
behavior for those actions (a fake search, a button that flips local state
without calling anything real) would violate this project's oldest and
most consistently applied discipline: never claim a capability works
without live evidence (the same rule that produced `FeatureUnavailableError`
over guessed ATS support, and kept `confirmation_id`/`confirmation_url`
`None` in ADR-0071 rather than fabricated). This is especially true for
submission: ADR-0071's countdown-plus-blocking-ENTER confirmation is a real
terminal interaction with no honest HTTP equivalent yet, and reproducing it
carelessly in a browser is exactly the risk ADR-0072 named as a reason to
defer write endpoints to their own explicitly-scoped decision.

## Decision

### Every page renders real data from the six existing routes, nothing else

`frontend/src/services/api.ts` is a one-function-per-route wrapper —
`applications()`, `reviews()`, `pendingReviews()`, `submissions()`,
`resumeVariants()`, `analyticsSummary()`, `settings()` — matching
`api/routers/*.py` exactly, field for field, typed by
`frontend/src/types/api.ts` (a hand-kept mirror of the Pydantic response
models, the same "types mirror the backend, not a redesign" discipline the
backend's own `analytics.py`/`settings_.py` already apply to their source
stores). TanStack Query hooks (`hooks/useApi.ts`) wrap each call; no page
component ever calls `fetch` directly.

Where a page needs data spanning more than one route (Review Queue showing
résumé/cover-letter/warnings alongside the approval decision; Submission
Queue's "ready to submit" list), the join is a **pure function** in
`lib/derive.ts` — `joinReviewsWithSessions`, `readyForSubmission`,
`countBy`, `applicationsPerDay` — over the already-fetched raw responses.
This mirrors `api/routers/analytics.py`'s own precedent exactly: a
`Counter` aggregation is presentation logic layered on existing data, not a
new source of truth; the same reasoning applies one layer up, in the
client. `readyForSubmission` in particular reuses two status values the
backend already returns (`approval_status === "APPROVED"`, and "no
`SubmissionResult` exists yet for this session") — it introduces no new
status vocabulary of its own.

### Write actions are named, not faked

`components/CliOnlyAction.tsx` is a disabled button carrying the exact real
CLI command in its `title` (`career-agent review --session <path>`,
`career-agent submit --review-session <path> ...`, `career-agent discover
--profile ...`). Every button the brief describes that has no backing route
— Search Jobs' Search, Review Queue's Approve/Reject, Submission Queue's
Submit — renders through this component. `components/ui/callout.tsx` gives
each page a short, honest explanation of *why*: Submission Queue states
plainly that there is no live browser state or countdown to show because
submission only happens inside a real, supervised terminal session this
dashboard cannot safely reproduce over HTTP; Search Jobs names that
discovery has no API endpoint yet; Dashboard/Analytics both flag that
interview/offer figures aren't available because that data lives on the
older, deliberately separate `SqliteApplicationStore`/outcome pipeline
ADR-0072 already documented as out of scope.

This is a real product limitation, not a placeholder to quietly forget:
approving a review, submitting an application, and triggering discovery
all remain exclusively CLI actions after this phase, exactly as they were
before it — a decision the frontend surfaces honestly rather than papering
over with dead buttons or fabricated success states.

### UI primitives, not the shadcn CLI

`components/ui/*` (`button`, `card`, `badge`, `input`, `select`, `table`,
`skeleton`, `callout`) are hand-written in the shadcn "copy the component
into your repo" style (`class-variance-authority` + `tailwind-merge`, no
external UI runtime dependency) rather than generated via `shadcn add`,
since this sandbox has no path to the shadcn registry's network endpoint.
Same visual/API contract shadcn ships, same reasoning as any other
"reused, not duplicated" primitive in this project.

### Vite dev server proxies `/api` to `career-agent serve`

`vite.config.ts` proxies `/api/*` to `http://127.0.0.1:8000` (`career-agent
serve`'s default bind) in development; the production build calls `/api/*`
as same-origin relative paths, so a reverse proxy or the FastAPI app itself
serving the built `dist/` (a later phase's decision, not this one's) both
work without a frontend code change.

### Backend and API are untouched

No file under `src/career_agent/` changes in this phase. Confirmed by
running the full backend suite unmodified before and after (990 passed,
matching Phase 54's count exactly) and by this phase adding zero new
Python files.

## What this phase explicitly does not do

- No write endpoint added to the FastAPI backend, and no client-side
  fabrication of one. Approving a review, rejecting a review, triggering
  discovery, and submitting an application all remain CLI-only.
- No live browser state, no countdown, no confirmation flow reproduced in
  the browser for submission — ADR-0071's terminal-only design is
  unchanged.
- No authentication (matches ADR-0072: single-user, localhost-only tool).
- No interview/offer tracking (that pipeline is out of scope, named
  honestly on-page rather than silently omitted).
- No code-splitting/lazy-loading pass — the production bundle is a single
  ~700 kB chunk (Vite's default warning threshold), acceptable for a
  single-user, localhost-served dashboard at this phase; named as a future
  revisit, not solved speculatively here.

## Consequences

- 15 new frontend tests (Vitest + React Testing Library): pure-function
  coverage for every `lib/derive.ts` join (`derive.test.ts`), a
  `CliOnlyAction` behavior test, and route/rendering smoke tests
  (`App.test.tsx`, `DashboardPage.test.tsx`) covering both the
  real-data-renders and the API-unreachable-shows-an-error-banner paths.
  All pass; `tsc -b`, `oxlint`, and `vite build` are all clean.
- Manually verified against a real, running `career-agent serve` process
  with seeded SQLite data (not just mocked fetches): Dashboard, Review
  Queue, and Submission Queue screenshotted in both light/dark themes and
  at a mobile viewport, confirming real API data renders correctly, the
  Submission Queue's "Ready" count correctly stayed at zero for a
  still-`WAITING` review, and the sidebar collapses to a mobile drawer.
- New CI job `verify-frontend` (matrix `ubuntu-latest`/`windows-latest`,
  matching the backend `verify` job's platform pair) runs `npm ci`, type
  -check, lint, `vitest run`, and `vite build` on every push/PR — the
  frontend is now gated the same way the backend always has been, not
  merely "builds on my machine."
- The dashboard is fully usable for what it's for today: seeing prepared
  applications, reviewing what a `career-agent prepare` run produced,
  seeing what has and hasn't been submitted, and browsing history/
  analytics — with every action that would need a write endpoint pointing
  the user at the exact CLI command instead of guessing.

## Future revisit criteria

- If a future phase adds write endpoints to the API (discover/approve/
  reject, and especially submit), `CliOnlyAction` usages become the map of
  exactly what needs wiring — each one names the route it's standing in
  for.
- If submission-over-HTTP is ever built, the countdown/confirmation UX
  needs its own explicit safety design, not a mechanical translation of
  the terminal flow — named as an open question in ADR-0072's own revisit
  criteria already.
- If the bundle-size warning becomes a real problem (slow first load on a
  weak machine), revisit route-based code-splitting then, with an actual
  measurement to justify it.
