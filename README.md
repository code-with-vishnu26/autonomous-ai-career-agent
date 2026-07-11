# Autonomous AI Career Agent

> A single-user, self-hosted assistant that discovers job openings, ranks them,
> ingests your CV as evidence, and **prepares** truthful, ATS-tuned application
> materials for your review — using **your** accounts, **your** data, and
> **your** machine.

This is **not** a mass job-application bot and **not** a multi-tenant SaaS. It is
a personal agent you own end-to-end. Its guiding principle is **quality over
volume**: fewer, sharper, *truthful* applications.

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

A **read-only** FastAPI layer (Phase 54, [ADR-0072](docs/adr/0072-web-dashboard-read-api.md))
over the same data the CLI already produces — `GET /api/applications`,
`/api/reviews` (and `/api/reviews/pending`), `/api/submissions`,
`/api/resume-variants`, `/api/analytics/summary`, `/api/settings`
(secrets redacted to a `configured: bool` flag, never their values). Each
route wraps exactly one existing store class; there is no duplicated
business logic here and no new database schema. Every route is a `GET` —
structurally enforced by a test that enumerates the app's actual routes —
so **nothing reachable through this API can trigger a search, a tailoring
run, a review approval, or a submission**; those remain exclusively CLI
actions (`discover`/`prepare`/`review`/`submit`). The React frontend
consuming this API is documented next.

## Web Dashboard frontend (`frontend/`)

```bash
# Terminal 1 -- the API this frontend consumes
pip install 'career-agent[web]'
career-agent serve

# Terminal 2 -- the dashboard itself
cd frontend
npm install
npm run dev   # http://localhost:5173, proxies /api to 127.0.0.1:8000
```

A React 19 + TypeScript + Vite dashboard (Phase 55, [ADR-0073](docs/adr/0073-react-dashboard-frontend.md))
over the Phase 54 API above — TailwindCSS + hand-written shadcn-style
primitives, TanStack Query, React Router, React Hook Form, Recharts, Lucide
icons. Eight pages: Dashboard, Search Jobs, Applications, Review Queue,
Submission Queue, History, Analytics, Settings. Responsive (sidebar
collapses to a mobile drawer) and dark-mode aware (persisted, defaults to
the OS preference).

**Every number on every page comes from one of the six existing `GET`
routes** — no client-side fabrication, no duplicated backend logic. Where a
page needs data joined across routes (e.g. Review Queue showing a résumé
preview next to its approval decision), the join is a pure function over
the already-fetched responses (`frontend/src/lib/derive.ts`), the same
"aggregation is presentation logic" precedent the API's own
`analytics.py` already established server-side.

**Actions with no backing endpoint are named, not faked.** Search Jobs'
Search button, Review Queue's Approve/Reject, and Submission Queue's Submit
all render as disabled buttons naming the exact CLI command to run instead
(`career-agent discover`/`review`/`submit`) — approving a review and
submitting an application stay exclusively CLI actions, preserving
ADR-0071's terminal-only countdown/confirmation gate untouched. Submission
Queue explicitly has no live browser state or countdown to show, for the
same reason.

Build for production with `npm run build` (output in `frontend/dist/`);
test with `npm test` (Vitest + React Testing Library); type-check with
`npx tsc -b`; lint with `npm run lint`.

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
