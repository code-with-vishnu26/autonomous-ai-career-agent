# ADR-0039: The Learn pillar — full outcome history, raw counts only, mandatory small-sample honesty

- **Status:** Accepted
- **Date:** 2026-07-04
- **References:** [ADR-0009](0009-learning-engine.md) (the learning
  engine's original charter), [ADR-0037](0037-persistence-discover-and-first-profile-writer.md)
  (the append-only outcome table this reads)

## Decision

**`career-agent outcome <app-id> viewed|response|interview|offer|rejection
[--stage]`**: typed kinds only (an unknown kind is refused, not stored);
outcomes attach only to applications the store actually recorded (a typo'd
id is refused, never an orphan row); appended to their own table — history
is never mutated.

**`career-agent report`** (`agents/learning/funnel.py`): per-variant
funnels keyed to `(prompt_version, profile_version, ATS band)` — the
three things that distinguish one application's content recipe from
another. The FULL outcome history is read: an application counts at every
stage it reached, and rejection *stages* are separated facts
(post-interview ≠ at-screen).

**Statistical honesty at personal N is the load-bearing guarantee:** raw
counts and funnel-stage conversion ONLY. No significance testing, no
Thompson sampling/bandit routing, no better/worse/recommended verdicts —
below N≈50 per variant (recorded as `MIN_N_FOR_COMPARISON`, visible data
not folklore) those are noise dressed as insight. "3/12 interviews vs
1/9" renders as exactly that. Every rendered report carries the explicit
small-sample caveat — injection-verified (dropping the caveat from
rendering was caught by two tests), and the no-verdict property is tested
by asserting the absence of prescriptive language in a rendered
comparison. Crossing into inferential territory at real N is its own
future pre-brief, never a threshold this module silently crosses.

## Future revisit criteria

- A variant genuinely reaches N≥50 → the inferential-stats pre-brief.
- Outcome kinds prove insufficient in real use (e.g. "recruiter screen"
  vs "onsite") → extend the typed set, never free text.
