# ADR-0084: Profile-Backed ATS / Keyword Scoring

- **Status:** Accepted
- **Date:** 2026-07-13
- **References:** [ADR-0075](0075-career-coach.md) (the deterministic
  keyword-coverage scorers this reuses unchanged -- `job_match_score`,
  `skill_gap_report`, `score_coverage`), [ADR-0082](0082-per-user-master-profile-onboarding.md)
  (the per-user Master Profile whose data this scores), [ADR-0083](0083-web-excel-export.md)
  (the immediately-prior "move the interface to the web" phase)

## Context

The originating request asked the agent to "check the ATS score, keywords"
for a job. An audit found this scoring **already exists in the web
dashboard**: the Career Coach's Job Match Score, Skill Gap, and Resume
Analysis pages (Phase 57, ADR-0075) all compute a *deterministic*
keyword-coverage score against a job description -- no LLM, no cost, no
fabrication risk.

The real gap was the input: those pages make the user **paste** their
résumé text every time. A user who just onboarded a Master Profile (Phase
64) has already told the system everything those scorers need; making them
paste it again is the friction, not the scoring.

**A repository-reality audit found:**

- `job_match_score(resume_text, jd_text)` and
  `skill_gap_report(resume_text, jd_text)` are pure functions over
  *résumé text* (`domain/coach_analysis.py::score_coverage`), with no LLM
  call. They only need a text blob of the candidate's content.
- The three deterministic coach endpoints already take a shared
  `ResumeJdRequest` and require only authentication -- no
  provider/promptfoo readiness, unlike the LLM-backed coach endpoints.
- No function rendered a `MasterProfile` to plain text; the tailoring
  pipeline (`prepare`) renders a full, LLM-tailored résumé artifact, far
  heavier than a keyword scorer needs.

## Decision

Add a profile-backed scoring path that reuses the existing deterministic
scorers, changing nothing about them.

- `domain/profile_text.py` (new, pure): `master_profile_to_resume_text`
  flattens a `MasterProfile` (summary, work positions + highlights,
  project names/descriptions/highlights/keywords, skill names + keywords,
  education) into the plain text the coverage scorer tokenizes. Lossy by
  design -- it preserves the *words*, not layout -- and explicitly **not**
  a résumé generator (tailoring stays the real artifact pipeline). Lives
  in `domain/` (imports only `domain/models`), so the layers contract
  holds.
- `POST /coach/profile-match` (new): takes only `{ jd_text }`, loads the
  caller's stored Master Profile, renders it to text, and returns the
  job-match score **and** skill-gap ranking together (both keyword-based,
  naturally read as "how well do I match, and what's missing"). Returns
  **404** when the caller has no profile yet -- so the UI sends them to
  onboarding rather than showing a misleading 0%. Deterministic, so it
  needs no provider configuration.
- Frontend: `coachApi.profileMatch` / `useProfileMatch`, and a new
  "Match My Profile" Career Coach page -- paste a JD, get the score,
  missing keywords, and prioritized skill gaps, with the 404 rendered as
  an onboarding prompt. No résumé paste.

## Consequences

- A user who onboarded can score their profile against any job with one
  paste of the JD -- the connective tissue between Phase 64's Master
  Profile and the existing ADR-0075 scorers, and a building block for the
  guided Apply Flow.
- The existing paste-based Job Match / Skill Gap / Resume Analysis pages
  are unchanged -- this is an additive path, not a replacement, for users
  who want to score an arbitrary résumé they haven't stored.
- The scoring stays deterministic and free: no LLM call is added, so this
  works with no provider configured (unlike the LLM-backed coach
  features).
- `master_profile_to_resume_text` is deliberately minimal; if a future
  need arises for a richer profile-to-text rendering (e.g. for a
  different consumer), it can grow, but it is not a résumé generator and
  should not become one -- `prepare` owns that.
