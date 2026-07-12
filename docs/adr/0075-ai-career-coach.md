# ADR-0075: AI Career Coach

- **Status:** Accepted
- **Date:** 2026-07-12
- **References:** [ADR-0034](0034-ats-score-gate.md) (`ats_scoring.py`, the
  keyword taxonomy this phase's deterministic checks reuse), [ADR-0016](0016-truthfulness-gate-verification.md)/[ADR-0043](0043-zero-cost-truthfulness-gate-provider.md)
  (`ClaimVerifier`, reused here to verify AI-drafted suggestions before they're
  shown), [ADR-0074](0074-authentication-and-multi-user-platform.md) (the
  `/auth/`/`/user/` write-capable-router precedent this phase's `/coach/*`
  extends), [ADR-0036](0036-worldwide-job-board-sources.md) (the standing "no scrapers"
  policy this phase's deferrals rely on)

## Context

The application automates job searching and applying. The user's brief asks
for a next step: help candidates become stronger, not just submit more --
ten named features (Resume Analysis, Job Match Score, AI Resume
Suggestions, Cover Letter Assistant, Company Research, Interview
Preparation, Skill Gap Analysis, Salary Insights, Weekly Career Report,
Career Roadmap), a new "Career Coach ⭐" sidebar section, and four hard
principles: never fabricate achievements, suggestions are advisory only,
users explicitly accept any change before it's applied, and every
suggestion explains why it was made.

A repository-reality audit (before any code was written) found six of the
ten features have a real, existing data source to build on
(`domain/ats_scoring.py`'s keyword taxonomy, the LLM provider abstraction,
`ClaimVerifier.verify_claim`) and four do not:

- **Company Research** needs employer/culture data. No such integration
  exists, and ADR-0036 is a standing policy against adding a scraper to get
  one.
- **Salary Insights** needs a compensation-benchmarking data source
  (Levels.fyi/Glassdoor/BLS-style API). None is integrated.
- **Weekly Career Report** and **Career Roadmap** both need outcome data
  (interviews, rejections, offers) to report or plan against. This
  project has two disconnected pipelines here: an old,
  CLI/Streamlit-only `SqliteApplicationStore.record_outcome`/
  `outcome_rows()` that was never exposed via FastAPI, and the newer
  `ApplicationSession`/`ReviewSession`/`SubmissionResult` stores the
  dashboard actually reads, which have no interview/rejection/offer
  concept at all. Reconciling them is a real, separate side-quest, not
  something this phase can absorb.

Building all ten "for real" today would mean either fabricating data for
four of them (directly violating the brief's own "never fabricate"
principle) or a materially larger scope than this phase's brief describes.
This was surfaced to the user as an explicit scoping question rather than
decided unilaterally, since it is a genuine product tradeoff, not an
implementation detail. **The user chose: build the six real features for
real; defer the other four with a named reason, still visible in the UI.**

## Decision

### Six features are built for real; four are explicitly deferred, not faked

Built: Resume Analysis, Job Match Score, AI Resume Suggestions, Cover
Letter Assistant, Interview Preparation, Skill Gap Analysis. Deferred:
Company Research, Salary Insights, Weekly Career Report, Career Roadmap --
each still has a sidebar entry and a page, and each page states in plain
language why the feature isn't available yet and what would need to
change for it to be, mirroring the `CliOnlyAction`/`Callout` precedent
Phase 55 established for naming an unavailable capability honestly instead
of a dead or fake button.

### A distinct, lighter deterministic pipeline: `domain/coach_analysis.py`

`ats_scoring.py::score_resume` scores an already-tailored, structured
`TailoredContent` against a full `MasterProfile`'s sections (contact,
education, contextual-vs-skills-only credit, stuffing detection) -- it
requires that whole structured shape as input. The Career Coach instead
needs to score arbitrary pasted/uploaded freeform resume text against a
job description, with no profile and no structured sections at all. Rather
than force that different input shape through `score_resume`'s private
matching helpers (built for a different, structured contract),
`domain/coach_analysis.py` is a new, smaller pure module: it reuses
`extract_jd_keywords` and the same curated `HARD_SKILLS`/`SOFT_SKILLS`
taxonomy (so the two pipelines never disagree about what a "hard"/"soft"
skill is), with its own simpler word-boundary occurrence check (no
stuffing cap, no contextual/skills-only credit split -- freeform text has
no section structure to distinguish). It also adds two heuristics that
have no existing home: `find_weak_bullets` (a fixed, curated action-verb
list plus a "has a digit" metric check) and `find_formatting_issues`
(empty text, tabs, missing email pattern, overlong lines) -- both
deterministic, both documented as heuristics, not model judgments.

Resume Analysis, Job Match Score, and Skill Gap Analysis (`agents/coach/
resume_analyzer.py`, `job_match.py`, `skill_gap.py`) are thin wrappers
over this module. None of the three makes an LLM call or carries any
fabrication risk.

### "Learning priority" is a named heuristic, not a ranking model

Skill Gap Analysis's `learning_priority` ranks missing keywords hard-skill-
first, then by how early each one first appears in the job description.
This is deliberately not a learned model: there is no outcome data
anywhere in this codebase to train one on (the same gap that got Weekly
Career Report and Career Roadmap deferred). Every ranked entry's `reason`
states exactly what was checked ("a hard skill requirement" / "mentioned
early in the job description"), so the ranking is inspectable rather than
a black box.

### A new, narrow LLM port: `CareerCoachAdvisor`

Every existing LLM port (`ContentDrafter`, `SemanticKeywordMatcher`,
`ClaimVerifier`) is narrowly typed to one resume-tailoring shape. The
Career Coach's three LLM-backed features (Resume Suggestions, Cover Letter
Assistant, Interview Prep) each need differently-shaped free text back, so
`core/interfaces.py::CareerCoachAdvisor` is intentionally the opposite: one
`draft_text(prompt) -> str` method, raising on failure rather than
returning a fabricated or empty string -- exactly `GroqContentDrafter`'s
"raise rather than fabricate" contract, generalized. `GroqCareerCoachAdvisor`/
`AnthropicCareerCoachAdvisor` wrap the same low-level `groq_chat_completion`/
`anthropic.AsyncAnthropic` clients every other port already uses;
`llm/providers.py::select_coach_advisor` follows the identical Groq-first/
Anthropic-second/raise-if-neither pattern as `select_content_drafter`. This
port makes no truthfulness guarantee on its own -- every caller is
responsible for verifying what comes back, which is the next decision.

### Every AI-drafted claim is verified by the same `ClaimVerifier` the truthfulness gate uses, before it is ever shown

This is how "never fabricate achievements" is actually enforced, not just
stated. `agents/coach/resume_suggestions.py` only ever asks the advisor to
*reword* an existing bullet (never invent a new fact/employer/number);
even so, every returned `{original, suggested}` pair is independently
re-checked via `ClaimVerifier.verify_claim(suggested, original)` before it
is surfaced, using the project's existing 0.7 confidence threshold
(`agents/resume/gate.py::_DEFAULT_CONFIDENCE_THRESHOLD`). A suggestion
that fails verification is silently dropped, not raised -- that is the
verifier correctly doing its job, not a system failure. The same pattern
verifies `agents/coach/cover_letter_assistant.py`'s rewrites against the
original letter body, this time raising a typed
`CoverLetterTransformRejectedError` (fail closed, never a silent fallback
to unmodified text) if verification fails. Both call sites reuse
`select_claim_verifier` and `verify_promptfoo_results` exactly as `cli.py`
already does before constructing any real verifier (ADR-0016/0043
discipline) -- a verifier is never constructed for real use here without a
live-validated promptfoo pass already on disk. Interview Preparation
(`agents/coach/interview_prep.py`) is the one LLM-backed feature with no
verifier call: its output is questions and general STAR guidance, never a
claim about the candidate, so there is no achievement to fabricate. Its
actual fabrication risk (a question implying something about the company
the JD doesn't support) is handled by the prompt itself requiring every
question's `why` to cite the specific JD text that prompted it.

### Nothing here is ever applied automatically -- "accept" is a local UI note, not a write

None of the six real features has a write path back into a résumé,
profile, or any stored record. Resume Suggestions and the Cover Letter
Assistant return advisory text; the frontend's Accept/Reject buttons on a
suggestion only flip local component state (`useState`) to help the user
track their own decision -- there is no backend endpoint that could apply
one even if a caller tried. This directly satisfies "users explicitly
accept any changes before they're applied": the honest answer is that
nothing here can ever apply a change without the user manually acting on
it themselves.

### `/coach/*`, not `/api/coach/*`

`test_dashboard_data_routes_are_get_only` structurally proves every
`/api/*` route is GET-only (ADR-0072) because none of them can trigger a
real action. Every Career Coach endpoint calls an LLM -- a real, costed
action, even though none of them write to a database -- so, exactly like
`/auth/*`/`/user/*` in Phase 56, `/coach/*` sits outside `/api/*` as a
third named write-capable-router exception
(`test_auth_and_user_are_the_only_write_capable_routers` now allows all
three prefixes). Every request is self-contained (resume/JD text in the
body); there is no server-side stored profile the API can read for an
arbitrary multi-user caller, so `/coach/*` never touches the database at
all -- the same "distinct, simpler pipeline" reasoning as
`domain/coach_analysis.py`.

## What this phase explicitly does not do

- **Company Research, Salary Insights, Weekly Career Report, Career
  Roadmap** are not built. Each has a sidebar entry and page that states
  why, per the scoping decision above. Building any of them for real is
  future work contingent on a real data source (Company Research, Salary
  Insights) or reconciling the two outcome-tracking pipelines (Weekly
  Career Report, Career Roadmap) -- not a decision this phase makes.
- No server-side storage of any Career Coach input or output. Every
  `/coach/*` call is stateless; nothing is persisted, so there is no
  history of past suggestions/analyses to browse. Adding that (if wanted)
  is a new, separate design question, not implied by anything here.
- No résumé/JD file upload -- every feature takes plain pasted text, the
  same scope restraint `domain/coach_analysis.py`'s docstring names.
- No change to `ats_scoring.py`, `domain/cover_letter.py`, or the real
  ATS-gated tailoring pipeline. The Career Coach is entirely additive and
  reads nothing from, writes nothing to, and cannot influence any
  existing pipeline.

## Consequences

- Backend: `domain/coach_analysis.py` (pure, no LLM); `agents/coach/`
  (`resume_analyzer.py`, `job_match.py`, `skill_gap.py`,
  `resume_suggestions.py`, `cover_letter_assistant.py`,
  `interview_prep.py`); `llm/coach_advisor.py` +
  `llm/groq_coach_advisor.py` + `select_coach_advisor`;
  `api/routers/coach.py` (`/coach/*`); 35 new backend tests (1104 total)
  (`tests/domain/test_coach_analysis.py`, `tests/agents/coach/*`,
  `tests/api/test_coach_router.py`); full suite, ruff, and lint-imports
  green.
- Frontend: a "Career Coach ⭐" sidebar section (11 entries: the overview
  page plus 6 real + 4 deferred features); `pages/coach/*`; `services/
  coachApi.ts`; `hooks/useCoach.ts` (`useMutation`, not `useQuery` -- every
  call is a user-triggered action, never fetched on page load); 3 new
  frontend tests; clean `tsc`/`oxlint`/`vite build`.
- Zero changes to any Phase 50-56 domain model, store, or existing router.

## Future revisit criteria

- If a real company-research or salary-benchmarking data source is ever
  integrated (a licensed API, not a scraper), Company Research/Salary
  Insights should be revisited against this ADR's deferral reasoning, not
  quietly built around it.
- If the old `record_outcome`/`outcome_rows` pipeline is ever reconciled
  with the dashboard's `ApplicationSession`/`ReviewSession`/
  `SubmissionResult` stores (a real, separate migration), Weekly Career
  Report and Career Roadmap become buildable without fabricating data.
- If Career Coach usage ever needs to be persisted (a history of past
  suggestions), design that storage layer explicitly then -- the current
  fully-stateless design is a deliberate scope restraint, not an
  oversight.
