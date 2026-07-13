# Autonomous AI Career Agent

> A self-hosted assistant that discovers job openings, ranks them, ingests
> your CV as evidence, and **prepares** truthful, ATS-tuned application
> materials for your review — using **your** accounts, **your** data, and
> **your** machine.

This is **not** a mass job-application bot. The CLI (`career-agent prepare`/
`review`/`submit`) remains the single-operator personal agent it has always
been — you own it end-to-end. The dashboard, as of Phase 60
([ADR-0078](docs/adr/0078-saas-multi-tenant-platform.md)), supports real
Organizations and teams for people who want to run this install for more
than one person — a deliberate, explicit mission change from this project's
original single-user-only framing, recorded (not hidden) in
[ADR-0000](docs/adr/0000-project-philosophy.md)'s own amendment note. Its
guiding principle is unchanged: **quality over volume**: fewer, sharper,
*truthful* applications.

**Released software (`v1.0.0`/`v1.1.0`) posture: `PREPARE_ONLY`.** The agent
prepares everything up to a human confirmation and then **stops** — the
tagged releases do **not** submit applications to any external system. See
[Scope & limitations](#scope--limitations) and
[ADR-0056](docs/adr/0056-v1-prepare-only-release-scope.md).

**Current `main` (v2 development) adds one, explicitly human-gated
exception: `career-agent submit`** (Phase 53, [ADR-0071](docs/adr/0071-human-approved-submission-engine.md)).
It is never autonomous — every single application requires its own
explicit review approval (`career-agent review`) *and* a final countdown
plus a blocking confirmation prompt immediately before the click. Nothing
is ever submitted without you, in the moment, saying so twice.

---

## What it does

| Capability | Responsibility |
|------------|----------------|
| **Discover** | Find real openings from open ATS APIs (Greenhouse / Lever / Ashby), YC `hiring.json`, Hacker News "Who's Hiring," company career pages, and a provider-abstracted web-search layer. Dedup and persist them. |
| **Decide** | Score and rank opportunities deterministically (Pareto + sensitivity analysis, hard exclusions); decide what's worth pursuing. |
| **Ingest** | Parse a CV (`.docx` / `.txt` / `.md`) into **unverified**, source-bound fact proposals. You confirm each one; only confirmed facts are promoted into your profile. |
| **Prepare** | Tailor a résumé from your profile, enforce a fabrication-detection **truthfulness gate**, run an **ATS score gate** with a bounded revision loop, render artifacts, and ask for a real human confirmation — then stop. |
| **Learn** | Track outcomes and funnel counts to inform future targeting. |

## Core commitments

- **Truthfulness is non-negotiable.** Résumé tailoring may only use facts present
  in your structured master profile (JSON Resume schema). A **fabrication-detection
  gate** blocks any application whose content isn't grounded in that profile — the
  job description is never treated as evidence. Unsupported skills, seniority,
  metrics, and action claims are rejected.
- **CV facts are untrusted until you confirm them.** Imported CV content becomes
  *proposals*, never silent profile edits. Promotion is fail-closed and never
  overwrites a different verified value (see
  [ADR-0052](docs/adr/0052-evidence-grounded-cv-ingestion.md)).
- **Prepare-only, by construction.** No automated executor is wired. Every
  `apply`/`auto` run ends at a confirmation boundary that refuses execution and
  reports "nothing was actually sent" (see
  [ADR-0050](docs/adr/0050-execution-safety-boundary.md) and
  [ADR-0054](docs/adr/0054-production-readiness-release-gate.md)).
- **Idempotent and recoverable.** A prior non-rejected attempt for the same
  opportunity is detected and skipped; runs are recorded in an append-only
  execution journal (ADR-0048 / ADR-0049).
- **Agent-oriented, not a fixed pipeline.** Capabilities register through a
  plugin registry + event bus, so new sources and adapters plug in without core
  rewrites.

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the full design and
[`docs/adr/`](docs/adr/) for the decisions behind it.

## Scope & limitations

| Area | v1.0 status |
|------|-------------|
| Discover, rank, ingest, confirm, promote, tailor, gate, ATS, render, journal, report, export | **SUPPORTED** |
| PDF CV import / OCR | **NOT_SUPPORTED** (`.docx` / `.txt` / `.md` only) |
| Browser submission / email-to-apply / autonomous external submission | **NOT_SUPPORTED** — code exists but is **unwired and unreachable** from the CLI |
| Live LLM output *quality* | Validated by a real controlled live-Groq smoke run (Phase 36) — CI itself never has an API key, so it can make **no** real LLM call |
| CI | Runs on every push/PR to `main`: lint, architecture contracts, full test suite, packaging, clean-install, and an offline CLI smoke — on **Linux and Windows** |
| macOS | **Untested** — a deliberate, documented gap, not silently dropped |

The full capability matrix and known limitations live in
[`docs/release/v1.0.0-notes.md`](docs/release/v1.0.0-notes.md).

## Tech stack

- **Language:** Python 3.11+
- **LLM providers:** Groq free tier (**preferred**: `openai/gpt-oss-120b` verifier,
  `llama-3.3-70b-versatile` drafter/matcher) with Anthropic Claude as a paid
  fallback (`claude-opus-4-8` / `claude-haiku-4-5-20251001`). Selection is
  fail-closed when no key is configured.
- **Storage:** SQLite + openpyxl (spreadsheet exports)
- **Prompt validation:** git-based prompt versioning + a fail-closed promptfoo
  regression gate keyed by prompt version and provider

## Quick start

**Only editable install from a cloned source checkout is currently verified.**
There is no PyPI package and no published GitHub Release asset yet — do not
`pip install` this from anywhere except a local clone.

Linux / macOS (bash/zsh):

```bash
git clone https://github.com/code-with-vishnu26/autonomous-ai-career-agent
cd autonomous-ai-career-agent
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # then add GROQ_API_KEY (preferred) or ANTHROPIC_API_KEY

career-agent setup     # scaffolds a starter profile + prints an offline readiness report
```

Windows (PowerShell):

```powershell
git clone https://github.com/code-with-vishnu26/autonomous-ai-career-agent
cd autonomous-ai-career-agent
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env   # then add GROQ_API_KEY (preferred) or ANTHROPIC_API_KEY

career-agent setup     # scaffolds a starter profile + prints an offline readiness report
```

Then edit `profile.json` with your real, truthful details and re-run
`career-agent setup`. The profile follows the
[JSON Resume](https://jsonresume.org/) schema — dates use its camelCase
convention (`startDate` / `endDate`, not `start_date`). An example work
entry (illustrating the shape — including an `endDate` for a past role,
which the scaffold omits for a current one) looks like:

```json
{
  "id": "w1",
  "name": "Acme Corp",
  "position": "Software Engineer",
  "startDate": "2023-01-01",
  "endDate": "2024-06-01",
  "highlights": ["Built and shipped a real feature"]
}
```

For a real Groq/Anthropic key to pass truthfulness validation, you also need
a local Promptfoo evidence run — see
[`promptfoo/README.md`](promptfoo/README.md) for the exact command;
`career-agent verify-promptfoo` checks the result it produces before `apply`
will use a real provider.

### Job Search Preferences (optional, before `discover`)

```bash
career-agent preferences
```

An interactive wizard for what kind of job you're looking for — titles,
seniority, location, salary, preferred/blacklisted companies, and more.
This is a **separate file** (`job_preferences.json`), never mixed into
`profile.json` — see [ADR-0064](docs/adr/0064-job-search-preferences-separate-from-profile.md)
for why. Once saved, `discover`/`auto` use it to generate targeted search
queries (e.g. "Backend Developer Remote", "Backend Developer India")
instead of one generic keyword. Re-running `career-agent preferences`
shows your current values and only changes what you answer — you never
have to re-enter everything. Most fields (salary, visa sponsorship,
company allow/deny lists, and a few behavior toggles) are captured now as
configuration for upcoming phases and are **not yet enforced** — the
wizard says so at each such prompt.

Core commands:

```
career-agent setup | preferences | import-cv | promote-cv | discover | apply | auto | prepare | review | submit
career-agent outcome | report | export | verify-promptfoo | diagnose-promptfoo-drift
```

`career-agent --help` lists them all. `apply` and `auto` prepare materials and
stop at confirmation; `prepare` additionally fills out a real application
form in a live browser and stops before Submit; `review` is the only place
a prepared application can be marked approved, and only by your own
explicit decision; `submit` is the only command that can click a real
Submit button, and only after `review`'s approval plus its own final
countdown-and-confirmation gate.

## Browser automation (foundation, not yet user-facing)

`career_agent.integrations.browser` provides low-level building blocks a
future browser-driven workflow will use: launching a real Chromium
instance (a persistent profile, or an ephemeral context seeded from an
already-saved, encrypted session), waiting for a human to log in (this
project **never** automates a login — it only observes whether one has
happened), and multi-tab tracking. There is no `career-agent` command that
uses this yet; it has no knowledge of jobs, résumés, or applications at
all (enforced by an import-linter contract, ADR-0065). Running it
requires a local Chromium build — `playwright install chromium` — and its
tests are skipped automatically if none is found.

## Website Adapter Framework (foundation, not yet user-facing)

`career_agent.integrations.adapters` provides a common interface over job
websites, so a future caller never has to switch on provider names — it
asks `AdapterRegistry.find(url)` for the right adapter. Supported
providers:

| Provider | Discovery (`search()`) | Resume upload | Cover letter | Easy apply |
|---|---|---|---|---|
| Greenhouse | ✅ real API | ❌ (verified: manual text field) | unverified | unverified |
| Lever | ✅ real API | ✅ (verified: required file upload) | unverified | unverified |
| Ashby | ✅ real API | unverified | unverified | unverified |
| RemoteOK / Remotive / Arbeitnow / The Muse | ✅ real API | unverified | unverified | unverified |
| Workday | ❌ stub (no integration exists yet) | unverified | unverified | unverified |

"Unverified" means *not yet confirmed against a live posting* — never
"confirmed absent." Discovery delegates to this project's existing,
real, API-based sources (the same ones `career-agent discover` already
uses); nothing here scrapes a job's title/description through a browser
except as a generic, universal (Open-Graph/`<title>`-based) fallback when
only a URL is known. There is no `career-agent` command that uses this
yet, no form-filling, and no login automation anywhere in this package
(ADR-0066).

**Adding a new adapter:** implement `WebsiteAdapter`
(`integrations/adapters/base.py`) — typically by inheriting
`BrowserAdapterMixin` for the browser-facing methods and wrapping a real
`OpportunitySource` for `search()` if one exists, or declaring an honest
`FeatureUnavailableError` stub (like `workday.py`) if it doesn't yet.
Register it with `AdapterRegistry`, and add its capability flags only
once verified against a real, live posting — never guessed.

## Search Planner (foundation, not yet user-facing)

`career_agent.agents.planner.planner.build_execution_plan` turns your Job
Search Preferences into an `ExecutionPlan` — an ordered, budget-bounded
list of (provider, query, limit, priority) search tasks — *before*
discovery runs, rather than searching every configured provider blindly.
It prioritizes providers you named in `preferred_ats_providers`,
diversifies across providers so no single one consumes the whole budget,
and deduplicates identical planned tasks. Purely deterministic: no LLM
call, no network, no adapter call (nothing here has ever seen a
`playwright` or `httpx` import — enforced by a test, not just claimed).
Nothing in this codebase executes the plan yet — that's future work; this
phase only builds the plan.

## Resume Variant Engine (foundation, not yet user-facing)

`career_agent.agents.resume.materials.ResumeVariantEngine` composes an
**unmodified** `ResumeTailoringPipeline` with two new, deliberately narrow
capabilities:

- `career_agent.domain.cover_letter.assemble_cover_letter` builds a cover
  letter **deterministically, with no new LLM call**: it copies the
  already-gate-approved résumé summary and up to three highlights verbatim
  into a letter shape. Extending the truthfulness gate itself to freeform
  prose is a real, separate problem, left for a future phase — nothing here
  can say anything the résumé doesn't already say.
- `career_agent.domain.resume_variants.select_closest_variant` ranks
  previously-approved résumé variants by deterministic keyword overlap
  against a job description, for inspection only. It is purely advisory:
  the tailoring pipeline always runs regardless of its answer, so it cannot
  influence what gets gated.

A new `SqliteResumeVariantStore` (alongside the existing application store
in `storage/sqlite.py`) persists approved variants, append-only. The engine
itself never touches storage — it returns a built résumé variant for the
caller to save, the same "pipeline doesn't touch storage either" shape the
existing tailoring pipeline already uses. There is no `career-agent`
command that uses this yet.

## Application Preparation (`career-agent prepare`)

```bash
career-agent prepare --profile profile.json --opportunity-file <path>
```

Tailors and gates a résumé, generates a cover letter (the Resume Variant
Engine above, unmodified), then opens a **real, visible** Chromium window,
navigates to the posting, and fills in as much of the application form as
it safely can:

- Known identity/résumé fields (name, email, résumé) are filled by the
  same per-platform `FormFiller` this project's Tier 2 apply machinery
  already uses (Greenhouse: real text fields; Lever: a real, required
  file upload of your rendered résumé; Ashby: an honest, unimplemented
  stub — its form selectors have never been verified against a live
  posting).
- Every other required field is classified (work-authorization/sponsorship
  questions are auto-answered only from a fact you've already explicitly
  captured; EEOC and anything else is never guessed) and, if it can't be
  safely resolved, listed for you to fill in yourself.
- If the site requires login and you supply a selector that detects it,
  `prepare` waits for **you** to log in on the visible window — it never
  automates a login, ever.

**It always stops there.** There is no code path anywhere in
`agents/application/engine.py` that clicks a submit button — proven by an
automated source scan, not just documented (ADR-0069). The result is a
stored `ApplicationSession` (status `READY_FOR_REVIEW`/`BLOCKED`/
`LOGIN_REQUIRED_TIMEOUT`/`UNSUPPORTED_PROVIDER`) with every filled field,
every uploaded file, every field still needing your attention, and any
warnings — for you to review. Nothing is ever submitted by this command.
`prepare` also writes the session to `<artifacts_dir>/sessions/<id>.json`
so you can hand it to `review` (below).

## Human Review (`career-agent review`)

```bash
career-agent review --session <artifacts_dir>/sessions/<id>.json
```

The **only** place a prepared application can be marked `APPROVED` — and
it only ever happens by your own explicit "y" answer. Prints a
deterministic summary (company, role, provider, uploaded files, filled
fields, **every** warning, **every** missing field — nothing is ever
hidden) and asks:

```
Approve? [y/N]:
```

Anything other than an explicit "y"/"yes" — including a blank answer — is
recorded as `REJECTED`, never treated as approval. Interrupting the
prompt (Ctrl+C) records `CANCELLED`. Every decision is written, append-only,
to your local database via `SqliteReviewSessionStore` (never overwritten,
never deleted).

`ReviewEngine` — the code behind this command — has **zero** dependency on
this project's browser automation: it never imports
`career_agent.integrations.browser` and never calls anything resembling a
click, proven by an automated source scan (ADR-0070), the same discipline
`prepare`'s no-submit-click guarantee already uses. It only ever records
what you decided. `review` also writes a JSON handoff to
`<artifacts_dir>/reviews/<id>.json` for `submit` (below) to consume.

## Submission (`career-agent submit`)

```bash
career-agent submit \
    --review-session <artifacts_dir>/reviews/<id>.json \
    --opportunity-file <path> \
    --profile <path>
```

**The only command in this codebase that can click a real Submit button** —
and only after every one of the following holds, checked fail-closed, in
order: the review and application session actually pair together; the
review is `APPROVED`; the application session is still `READY_FOR_REVIEW`;
the résumé about to be submitted is verified, content-for-content, against
what was stored when you reviewed it (a profile edit in between refuses,
never silently submits something different); the platform is one this
project has an actual human-in-the-loop browser flow for (Greenhouse,
Lever, Ashby today — everything else, including every job board and
Workday, refuses rather than guesses); and there is no unsafe prior
outcome for this opportunity (a previous submission, or an unresolved
uncertain one, permanently blocks an automatic retry).

Only once every one of those holds does it ask you anything:

```
Submitting in
5...
4...
3...
2...
1...
Press ENTER to continue (Ctrl+C to cancel):
```

Reuses `BrowserApplicator` (Phase 7b3/8g) — the real, tested Tier-2
executor that has existed in this codebase since early on, unwired from
the CLI specifically pending this fail-closed gate — unchanged. **No
success page, confirmation number, or "Thank you" banner has ever been
verified against a real, live posting on any platform in this project**,
so none is fabricated: the only verified signal is whether the submit
click completed with no challenge visible afterward. Every outcome
(`SUBMITTED`/`FAILED`/`UNKNOWN`/`ABORTED`/`CANCELLED`/`REFUSED`) is
recorded, append-only, via `SqliteSubmissionResultStore`, exportable via
`storage.excel.export_submissions`.

## Web Dashboard API (`career-agent serve`, backend only)

```bash
pip install 'career-agent[web]'
career-agent serve --host 127.0.0.1 --port 8000
```

A FastAPI layer over the same data and service layer the CLI already
uses. The `/api/*` prefix (Phase 54, [ADR-0072](docs/adr/0072-web-dashboard-read-api.md))
stays **read-only** by structural test (every `/api/*` route is a `GET`,
enforced by a test that enumerates the app's actual routes):
`GET /api/applications`, `/api/submissions`, `/api/resume-variants`,
`/api/analytics/summary`, `/api/settings` (secrets redacted to a
`configured: bool` flag, never their values). Discover, Review, and
Submit moved off that boundary in Phase 63
([ADR-0081](docs/adr/0081-web-triggered-discover-review-submit.md)) —
each calls the *exact same* function the CLI does, never a
reimplementation: `POST /discover` runs `build_discovery_sources`/
`run_discover_command` in the background, polled via `GET /discover/{run_id}`
(`/discover/runs`, `/discover/opportunities`); `GET /reviews/pending` +
`POST /reviews/decide` call `ReviewEngine` (one decision per session,
409 on a second attempt); `POST /submissions/prepare` +
`POST /submissions/{token}/confirm` call `submit_prepared_application`/
`SubmissionEngine` with the exact same fail-closed preconditions and a
real, un-bypassable human-confirmation gate (a bounded wait, 5-minute
timeout, silence never implies "yes" — never auto-confirms).
`career-agent prepare` (tailoring) remains CLI-only; `career-agent
discover`/`review`/`submit` remain fully available too — the CLI is a
supported power-user interface, not replaced. The React frontend
consuming this API is documented next.

## Web Dashboard frontend (`frontend/`)

```bash
# Terminal 1 -- the API this frontend consumes
pip install 'career-agent[web]'
JWT_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" career-agent serve

# Terminal 2 -- the dashboard itself
cd frontend
npm install
npm run dev   # http://localhost:5173, proxies /api, /auth, /user, /coach to 127.0.0.1:8000
```

A React 19 + TypeScript + Vite dashboard (Phase 55, [ADR-0073](docs/adr/0073-react-dashboard-frontend.md);
accounts added in Phase 56, [ADR-0074](docs/adr/0074-authentication-and-multi-user-platform.md))
over the API above — TailwindCSS + hand-written shadcn-style primitives,
TanStack Query, React Router, React Hook Form, Recharts, Lucide icons.
Eight pages: Dashboard, Search Jobs, Applications, Review Queue,
Submission Queue, History, Analytics, Settings, plus Login/Register/
Forgot-Password/Reset-Password/Profile/Account, plus a "Career Coach ⭐"
section (Phase 57, see below). Responsive (sidebar collapses to a mobile
drawer) and dark-mode aware (persisted, defaults to the OS preference,
applied on every page including the public auth ones).

**Every number on every dashboard page comes from an authenticated
caller's own data** — no client-side fabrication, no duplicated backend
logic, no cross-account leakage (every route filters by the caller's
`user_id`, proven by a dedicated isolation test). Where a page needs data
joined across routes (e.g. Review Queue showing a résumé preview next to
its approval decision), the join is a pure function over the
already-fetched responses (`frontend/src/lib/derive.ts`), the same
"aggregation is presentation logic" precedent the API's own
`analytics.py` already established server-side.

**Search Jobs, Review Queue, and Submission Queue are real, web-triggered
workflows (Phase 63, [ADR-0081](docs/adr/0081-web-triggered-discover-review-submit.md)).**
Search Jobs saves your filters to Job Search Preferences, then triggers
and polls a discovery run, listing real results. Review Queue's
Approve/Reject requires an explicit confirm step before calling
`POST /reviews/decide` — the same `ReviewEngine` the CLI uses. Submission
Queue's Submit starts a real attempt (`POST /submissions/prepare`), polls
its status, and only proceeds after an explicit `POST
/submissions/{token}/confirm` — the same fail-closed
`SubmissionEngine`/`domain/execution.py` gate ADR-0071 built, with the
same never-auto-confirm-on-silence discipline, just reached over HTTP
instead of a terminal countdown. **Preparing** a résumé/cover letter for
a result (`career-agent prepare`) still renders as a disabled button
naming the exact CLI command — it has its own real headed-browser
complexity not yet migrated.

**Master Profile onboarding is a real web wizard (Phase 64,
[ADR-0082](docs/adr/0082-per-user-master-profile-onboarding.md)).** A
dashboard account no longer needs `profile.json` or a terminal to tell
the system who they are: `/onboarding` is an 8-step wizard (Welcome →
Personal → Work → Education → Skills → Projects → Legal → Review) backed
by `GET`/`PUT /user/master-profile` and a new `SqliteMasterProfileStore`
(mirrors `SqliteUserPreferencesStore`), independent of the CLI's
`profile.json` by design — the two are never synchronized. The wizard
pre-fills from any existing stored profile, so it's safe to revisit, not
a one-time-only flow, and its final step links to the existing Job
Preferences and Notification Settings pages rather than duplicating
them. CV upload (`import-cv`/`promote-cv`) remains CLI-only for now — it
needs new multipart-upload infrastructure this phase didn't build.

Once you've onboarded, the Career Coach's **Match My Profile** page
(Phase 66, [ADR-0084](docs/adr/0084-profile-backed-ats-scoring.md)) scores
that stored profile against any job description — a deterministic ATS
keyword-coverage score and prioritized missing skills, no résumé paste and
no LLM cost. It reuses the exact same scorers the paste-based Job Match /
Skill Gap pages use.

**Excel download is web-native (Phase 65,
[ADR-0083](docs/adr/0083-web-excel-export.md)).** The formatted,
filterable application-tracker workbook the CLI has produced since Phase
13 is now a one-click download in the browser: the Applications page
exports your prepared applications and the History page exports your
submissions, each scoped to your own rows (`GET /export/applications.xlsx`
/ `GET /export/submissions.xlsx`, read-only). `career-agent export` still
works identically for CLI users.

Build for production with `npm run build` (output in `frontend/dist/`);
test with `npm test` (Vitest + React Testing Library); type-check with
`npx tsc -b`; lint with `npm run lint`.

## Authentication & accounts

`career-agent serve` refuses to start signing tokens without
`JWT_SECRET_KEY` set (fail-closed — no shared default secret). Register
via the dashboard (`/register`) or `POST /auth/register`; access tokens
(15 min) are held in memory by the browser (never `localStorage`),
refresh tokens (30 days, rotate on every use) live in an httpOnly cookie.
Every dashboard route requires a session; each account sees only its own
applications/reviews/submissions/résumé variants/preferences. The CLI is
unaffected — `career-agent prepare`/`review`/`submit` have no login flow
and continue to operate as a single, real, auto-provisioned "local
operator" account (`CLI_LOCAL_USER_EMAIL`, `.env`-overridable). Password
resets issue a real token but don't email it yet (no transport is wired —
a future phase); ask whoever runs the install for the token in the
meantime.

## Career Coach (Phase 57, [ADR-0075](docs/adr/0075-ai-career-coach.md))

Advisory, candidate-strengthening features under a new "Career Coach ⭐"
sidebar section, reachable once logged in. Every request is stateless and
self-contained (paste your resume text and a job description; nothing is
stored server-side):

- **Resume Analysis** — deterministic ATS-style score, missing keywords,
  weak-bullet flags, and formatting checks. No LLM call.
- **Job Match Score** / **Skill Gap Analysis** — the same deterministic
  keyword-coverage engine (`domain/coach_analysis.py`), plus a documented
  "learning priority" heuristic (hard skills first, then earliest JD
  mention — not a learned ranking model).
- **AI Resume Suggestions** — LLM-drafted rewordings of your *existing*
  bullets, each independently re-verified against your original text by
  the same truthfulness-gate `ClaimVerifier` before being shown. An
  unverifiable suggestion is dropped, never surfaced. Accept/Reject is a
  local note for you; nothing is ever written back automatically.
- **Cover Letter Assistant** — rewrite/shorten/more-formal/more-technical,
  verified the same way against your original letter.
- **Interview Preparation** — technical/behavioral/role-specific
  questions plus STAR guidance, grounded only in the job description you
  paste (never invented outside knowledge about the company).

**Four features named in the brief are deferred, not faked**: Company
Research, Salary Insights, Weekly Career Report, and Career Roadmap each
have a sidebar page that honestly explains why (no real company-research/
salary-benchmarking data source is integrated, and this project's
interview/rejection outcome tracking was never connected to the
dashboard) — see ADR-0075 for the full reasoning and revisit criteria.

Requires `GROQ_API_KEY` or `ANTHROPIC_API_KEY` (same as every other LLM
feature); the deterministic features (Resume Analysis, Job Match Score,
Skill Gap Analysis) work without either.

## Production Deployment (Phase 59, [ADR-0076](docs/adr/0076-production-deployment-and-infrastructure.md))

```bash
docker compose up --build   # http://localhost — backend, frontend, and an edge nginx proxy
```

Multi-stage `Dockerfile.backend` (gunicorn + uvicorn workers, non-root,
Playwright's Chromium installed) and `Dockerfile.frontend` (nginx-served
static build, non-root), fronted by a small edge reverse-proxy container
(`deploy/nginx/`) that routes `/` to the frontend and
`/api`/`/auth`/`/user`/`/coach`/`/health`/`/ready`/`/metrics` to the
backend. New `/health` (liveness), `/ready` (readiness — verifies the
real SQLite database is reachable, returns `503` rather than a false
`200`), and `/metrics` (Prometheus text format) endpoints; structured
JSON logging (`ENVIRONMENT=production`); a `docker` CI job that builds
every image for real and verifies Playwright's Chromium actually
launches inside the backend image.

`docker-compose.dev.yml` overlays hot reload (source mounted, Vite dev
server); `docker-compose.prod.yml` overlays resource limits and secure
cookies. `postgres`/`redis` containers exist and are startable
(`--profile postgres`/`--profile redis`) but are **not yet consumed by
the application** — the storage layer is SQLite-only today; see
ADR-0076 for why real PostgreSQL support was explicitly deferred rather
than built by duplicating or rewriting `storage/sqlite.py`.

See [`docs/deployment/docker.md`](docs/deployment/docker.md) (quick
start, dev/prod overlays, browser-automation-in-Docker caveats),
[`docs/deployment/production.md`](docs/deployment/production.md) (HTTPS,
backups, troubleshooting), [`docs/deployment/environment.md`](docs/deployment/environment.md)
(every variable, across `.env.example`/`docker.env`/`production.env.example`),
and [`docs/deployment/monitoring.md`](docs/deployment/monitoring.md)
(health endpoints, structured logs, Prometheus metrics).

## Notifications & Background Processing (Phase 58, [ADR-0077](docs/adr/0077-notifications-and-background-processing.md))

A real Notification Center, reachable from the bell icon in the navbar or
`/notifications`. Notifications are generated for events that have a
real, wired data source: a résumé is prepared, a review is approved or
rejected, a submission completes/is cancelled/fails, and a password
reset completes. In-app delivery works with no configuration; email
requires `SMTP_HOST`/`SMTP_FROM_ADDRESS` (unset by default — an attempted
email without SMTP configured is recorded as **skipped**, never
fabricated as sent); a webhook URL (`/notification-settings`) delivers to
any service that accepts an incoming JSON POST, including Slack, Discord,
and Microsoft Teams incoming webhooks. Browser push notifications use the
real browser `Notification` API client-side, with graceful degradation
where it's unsupported.

A background scheduler (`career-agent serve`'s own process, no separate
worker) runs six jobs: reminders (pending review, pending submission,
missing Promptfoo validation — every 60 min by default,
`REMINDER_INTERVAL_MINUTES`), daily/weekly digests (prepared/awaiting-
review/submitted counts, 08:00 UTC), notification cleanup (deletes
already-read notifications past `NOTIFICATION_RETENTION_DAYS`, default
30), expired refresh/password-reset token cleanup, and failed-webhook
retry. **The scheduler can never trigger a submission** — proven by an
AST-based structural test, not just a docstring promise; every job only
ever reads existing stores and writes to the notification stores.

Per-user preferences (`/notification-settings`) control which channels
are enabled, whether reminders/digests are on, quiet hours (channel
delivery pauses; notifications are still recorded, never lost), and the
webhook URL. **Several events named in early planning have no real
trigger point in this codebase and are not built**: a job-discovery
notification (discovery is now web-triggerable, see below, but nothing
notifies on a completed run yet), application-outcome notifications
(`career-agent outcome` remains a CLI-only pipeline), interview reminders
and incomplete-profile reminders (no interview-tracking or profile-
completeness store exists), and an expired-API-key notification (no
key-expiry concept exists) — see ADR-0077 for the full list and revisit
criteria. (Invitation notifications were deferred here for the same
reason — no invitation system existed yet — but Phase 60/ADR-0078 built
a real one; `invitation_received` is now a genuinely wired notification
category, see below.)

## Organizations & Team Management (Phase 60, [ADR-0078](docs/adr/0078-saas-multi-tenant-platform.md))

Every account belongs to at least one **Organization** — a real personal
one is created automatically at registration (you as its owner), so
nothing extra is required to start. Create more from `/organizations`,
where you can also see every organization you belong to and your role in
each.

Five fixed roles, each with a fixed permission set:

| Permission | owner | admin | recruiter | member | viewer |
|---|:---:|:---:|:---:|:---:|:---:|
| View dashboard / analytics | ✅ | ✅ | ✅ | ✅ | ✅ |
| Search, prepare, review, submit | ✅ | ✅ | ✅ | ✅ | — |
| Manage own notification settings | ✅ | ✅ | ✅ | ✅ | — |
| Invite / suspend users | ✅ | ✅ | — | — | — |
| Manage billing | ✅ | ✅ | — | — | — |
| Delete organization / transfer ownership | ✅ | — | — | — | — |

From `/organizations/<id>/team` you can invite members by email (a real,
hashed-token invitation — reused through the exact same Phase 58 email
transport and notification pipeline whenever the invited email already
has an account), change roles, remove members, and review/revoke/resend
pending invitations. Invitations respect your plan's seat limit — a real
`402 Payment Required`, not just a displayed number.

`/organizations/<id>/billing` is a real, production-ready billing
**shape** with **no Stripe integration and no external payment call
anywhere in this codebase** — three fixed plans (Free/Pro/Enterprise),
plan changes that activate immediately (there's no real payment to wait
for), and a live seat-usage counter. See ADR-0078 for exactly how it's
built so a real payment processor could be swapped in later without
touching any call site.

`/organizations/<id>/audit` shows every real mutation recorded for that
organization (who did what, when, from which IP, and whether it
succeeded) — an append-only log, never editable.

A platform-admin surface (`/admin`, visible only to accounts with the
platform-wide `admin` account flag — a separate concept from any
organization's own owner/admin role) lists every organization on the
install and its members.

**This is also a mission change, not just a feature**, and is recorded
as one: [ADR-0000](docs/adr/0000-project-philosophy.md) (this project's
founding philosophy) explicitly ruled out multi-tenancy "by fiat" until
now; ADR-0078 documents exactly why and how that changed, with the
original ADR-0000 decision text left untouched (see its Status line).
The CLI is unaffected by any of this — `career-agent prepare`/`review`/
`submit` remain the single local-operator, self-hosted tool they have
always been; organizations are a dashboard/API concept only.

## Production Hardening (Phase 61, [ADR-0079](docs/adr/0079-production-hardening.md))

With the roadmap feature-complete, this phase hardens what already exists
instead of adding scope. Every API response carries an `X-Request-ID`
header (reused from the caller if one was already set, generated
otherwise), and every structured log line produced during that request
carries the same ID — including a background job the request triggered.
An unhandled exception anywhere in the API now returns a safe, consistent
`{"detail": "Internal server error", "request_id": "..."}` body instead of
a bare 500, and always reaches this project's own structured logger with a
full traceback first. Both nginx layers (`deploy/nginx/edge.conf` and
`frontend.conf`) now set a real Content-Security-Policy alongside the
existing `X-Content-Type-Options`/`X-Frame-Options`/`Referrer-Policy`
headers. CI gained three real, always-run gates: `pip-audit` (with 20
CVEs in two `browser-use`-pinned transitive dependencies individually
named and ignored — a genuine upstream constraint, verified against the
latest available `browser-use` release, not a shortcut), `npm audit`
(genuinely clean today), and a committed `.secrets.baseline` +
`scripts/check_secrets_baseline.py` that fails CI on any newly introduced
potential secret. Existing rate limiting (auth-only) and the CSRF decision
(`SameSite=Lax`, no token) were re-examined and reaffirmed, not reopened.

## Browser Automation Robustness (Phase 62, [ADR-0080](docs/adr/0080-browser-automation-robustness.md))

Continuing Phase 61's hardening direction into the Submission Engine's
real, live-browser code path. A transient Playwright timeout during page
navigation or field-filling now retries up to 3 times before giving up —
**the submit click itself is never retried**, since retrying it risks a
second real-world submission if the first attempt actually succeeded but
responded slowly; never-submit-twice
(`domain/execution.py`, ADR-0048/ADR-0050) is unchanged and untouched.
Any browser-action failure now captures a screenshot, the page's HTML,
and its console log to `data/artifacts/browser_failures/` (configurable),
recorded on the resulting `SubmissionResult.diagnostics_dir` — so a
`FAILED`/`UNKNOWN` submission leaves something to actually look at. Found
and fixed along the way: `BrowserApplicator`'s submit-click and both of
`resume()`'s click-completing paths previously had **no exception
handling at all**, leaking an open, unclosed browser on any failure
there — now closed cleanly every time, matching the behavior every other
failure path already had.

## Privacy

Your profile, CV proposals, SQLite database, spreadsheet exports, rendered
résumés, and any promptfoo result artifacts stay on your machine. They are
git-ignored and never committed or packaged (see [`SECURITY.md`](SECURITY.md)).

## Status

**v1.1.0** — released (annotated `v1.1.0` tag pushed and a published GitHub
Release). It is a minor, supervised, prepare-only release on top of
[`v1.0.0`](docs/release/v1.0.0-notes.md): a portability, packaging, and
onboarding hardening pass with one new backward-compatible config field and
**no LLM-facing change** (Phases 40–45). Software release state is
`RELEASED`; the product's `PREPARE_ONLY` submission posture — it never
submits to any external system — is unchanged. See
[`docs/release/v1.1.0-notes.md`](docs/release/v1.1.0-notes.md),
[`ROADMAP.md`](ROADMAP.md), and
[`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md).

## License

[MIT](LICENSE) — built to be self-hosted and owned by the person running it.
