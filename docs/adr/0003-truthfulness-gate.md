# ADR-0003: Truthfulness gate (fabrication detection)

- **Status:** Accepted
- **Date:** 2026-06-30
- **References:** [ADR-0000](0000-project-philosophy.md) (Golden Rule #5),
  [ADR-0006](0006-json-resume-master-profile.md) (source of facts)

> This is the most important ADR in the project. Truthfulness is non-negotiable.

## Context

The Resume Agent uses an LLM to tailor applications. LLMs fabricate plausibly —
inventing skills, inflating dates, or claiming employers the user never worked
for. For this project that is unacceptable: a single fabricated claim can cost the
user an offer or their reputation, and it violates the project's core thesis
(truthfulness over optimization, [ADR-0000](0000-project-philosophy.md)).

## Problem

How do we guarantee — not hope — that **no** applicant-facing content leaves the
system unless every claim in it is grounded in the user's own verified facts, and
how do we make every rejection explainable to the user?

## Decision

Introduce a **truthfulness gate**: a hard, non-bypassable blocker that every piece
of generated applicant-facing content must pass before it can be used. The
**JSON Resume master profile** ([ADR-0006](0006-json-resume-master-profile.md)) is
the **only** source of facts. The gate is a guard, not a warning — failing content
is **never** submitted.

### Per-statement evidence and confidence

Generated content is decomposed into atomic **statements**. Each statement is
linked to **evidence** in the master profile and assigned a **confidence score**;
only sufficiently grounded statements survive.

```
Statement  →  Evidence (profile reference)  →  Confidence  →  Verified?
```

Examples:

```
"Built CI/CD with Docker"   source: profile.skills["Docker"]      confidence: 100%   ✅ verified
"5 years of AWS experience" source: (none)                        confidence: 0%     ⛔ blocked
```

A statement with no traceable evidence scores 0% and is blocked. The application as
a whole is blocked if **any** statement falls below the configured confidence
threshold (default: full grounding required for factual claims). This makes every
sentence traceable back to a fact the user actually attested to.

### Explainability

A rejection is never a bare verdict. The gate returns a structured, human-readable
explanation so the user knows exactly what to fix:

```
Rejected
  reason:   "unsupported claim"
  statement:"5 years of AWS experience"
  evidence: missing            # no matching profile entry
  detail:   skill "AWS" not found in master profile
```

Categories include: skill-not-found, evidence-missing, employer-mismatch,
date-inconsistency, and quantity/metric-unsupported. The user can then either
correct the profile (if the fact is true and merely absent) or accept that the
claim cannot be made.

## Alternatives considered

- **Trust the LLM / prompt it to "only use provided facts."** Prompting reduces but
  never eliminates fabrication; there is no guarantee. Rejected as a primary
  control (still used as defense-in-depth).
- **Whole-document LLM "is this truthful?" check.** Cheaper but opaque and itself
  fallible; can't point to the offending claim. Rejected as the sole mechanism;
  may assist as one signal feeding a statement's confidence.
- **Soft warnings instead of a hard block.** Contradicts the non-negotiable rule;
  a tired user would click through. Rejected.

## Trade-offs

- **(+)** A hard guarantee aligned with the mission; fully explainable rejections;
  decomposition makes the system auditable claim-by-claim.
- **(−)** Statement decomposition + evidence linking is real engineering effort and
  adds latency/cost per application; an over-strict gate may reject legitimate
  phrasings (mitigated: the fix is to enrich the profile, and thresholds are
  configurable per claim type, never disable-able to zero for factual claims).

## Consequences

- The master profile becomes load-bearing: richer profile ⇒ more that can be
  truthfully said. This reinforces [ADR-0006](0006-json-resume-master-profile.md).
- The gate sits on the Apply path as a mandatory step before any submission tier
  ([ADR-0010](0010-hybrid-application-strategy.md)).
- The Learning engine can track which claims get blocked most to suggest profile
  enrichment.

## Future revisit criteria

Revisit if:

- A reliable formal/grounding method supersedes statement-level confidence scoring.
- Confidence thresholds prove systematically wrong (too strict/lax) against real
  outcomes.
- New content types (e.g. cover letters, recruiter answers) need their own
  grounding rules.
- Per-application latency/cost from decomposition becomes prohibitive at the user's
  volume (note: this would never justify weakening the guarantee, only optimizing
  how it is computed).
