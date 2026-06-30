# ADR-0006: JSON Resume master profile

- **Status:** Accepted
- **Date:** 2026-06-30
- **References:** [ADR-0000](0000-project-philosophy.md),
  [ADR-0003](0003-truthfulness-gate.md)

## Context

Every application the system produces makes factual claims about the user: skills,
employers, dates, achievements, education. The truthfulness gate
([ADR-0003](0003-truthfulness-gate.md)) can only work if there is a single,
structured, machine-checkable record of what is true. We need to decide the format
and role of that record.

## Problem

What is the authoritative source of the user's facts, in what format, and how does
the rest of the system relate to it?

## Decision

Adopt a **single master profile** in the **[JSON Resume](https://jsonresume.org/)
schema** as the **single source of truth**. Everything applicant-facing derives
from it; nothing factual may originate elsewhere.

- **Single source of truth.** Résumés, cover letters, recruiter answers, and
  application form fields are all *projections* of the master profile. Generated
  content adds phrasing and emphasis, never new facts.
- **Standard schema.** JSON Resume is an established, documented, tooling-friendly
  open standard — better than a bespoke format for portability, validation, and
  ecosystem exporters.
- **Validated on load.** The profile is loaded and validated (schema + Pydantic
  models, Phase 5). Invalid profiles fail fast.
- **The grounding substrate.** Every statement the truthfulness gate verifies
  resolves to a reference into this document
  (`profile.work[].name`, `profile.skills[].name`, `profile.education[]`, …). A
  richer profile ⇒ more that can be said truthfully.
- **User-owned and local.** It is the user's data on the user's machine, never
  committed to the repo (see `.gitignore`); an example profile ships for docs/tests.

## Alternatives considered

- **Bespoke custom schema.** Maximum flexibility, but no ecosystem, more
  maintenance, and reinvents a solved problem. Rejected.
- **Unstructured documents (PDF/DOCX/free text) as the source.** What users already
  have, but not machine-checkable — fatal for the truthfulness gate. Rejected as the
  source of truth (may be an *import* path that populates the structured profile).
- **Multiple per-role profiles as sources.** Encourages divergence and duplicated
  facts that drift. Rejected: one master profile; role targeting is a projection,
  not a separate source.

## Trade-offs

- **(+)** Standard, portable, validatable; makes truthfulness enforceable; one place
  to maintain; clean separation of facts (profile) from phrasing (generation).
- **(−)** Users must invest in structuring their data up front; JSON Resume may not
  natively model every nuance (handled via documented extensions/custom fields,
  kept minimal); import from existing résumés is its own effort (later phase).

## Consequences

- This ADR and [ADR-0003](0003-truthfulness-gate.md) are mutually reinforcing: the
  gate is only as good as the profile is complete.
- Phase 5 delivers the loader/validator and the example profile; the truthfulness
  gate consumes its references.
- "Enrich your profile" becomes the standard remedy when a true claim is blocked
  for lack of evidence.

## Future revisit criteria

Revisit if:

- The JSON Resume schema is deprecated or proves too limiting for needed claim
  types.
- We need to represent facts JSON Resume can't model even with extensions.
- Multiple distinct factual personas (not just targeting) become a genuine
  requirement.
- A profile import pipeline (PDF/LinkedIn → structured) warrants its own ADR.
