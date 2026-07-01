# ADR-0011: Structured tailored resume content

- **Status:** Accepted
- **Date:** 2026-07-01
- **References:** [ADR-0003](0003-truthfulness-gate.md) (per-statement evidence),
  [ADR-0006](0006-json-resume-master-profile.md) (JSON Resume master profile)

## Context

While designing the Phase 2 domain models, `TailoredResume` was initially specced
with `content: str` — a free-text résumé body. Two downstream requirements were
already committed to by earlier ADRs and immediately conflicted with that choice:

- **The truthfulness gate** ([ADR-0003](0003-truthfulness-gate.md)) verifies content
  as atomic `Statement`s, each linked to an `EvidenceRef` in the master profile.
  Free text has no atomic statements — it must first be re-parsed into claims
  before it can be verified, on every verification, with no guarantee the parse is
  stable or matches what was actually generated.
- **A future diff viewer** (surfacing what changed between the master profile and a
  tailored résumé) is far cheaper over structured, section-shaped data than over
  prose: structural diffing is tractable; prose diffing is noisy and unreliable.

Both of these were foreseeable *before* any code bound to the free-text shape, which
is exactly the moment an ADR should catch this kind of mismatch.

## Problem

What should `TailoredResume` hold as its content, such that both the truthfulness
gate and a future diff viewer can operate on it without re-parsing prose, while
still allowing rendering to whatever final format an application actually needs
(plain text, PDF, an ATS form field)?

## Decision

`TailoredResume.content` (and its unverified precursor,
`TailoredResumeDraft.content`) is a **structured, JSON-Resume-shaped type**
(`TailoredContent`), not free text.

- `TailoredContent` mirrors the master profile's shape: a `summary`, a list of
  `TailoredWorkEntry` (each with a `source_entry_id` pointing back at the
  `MasterProfile` entry it was built from), a list of tailored skills, and a list of
  `TailoredProjectEntry`.
- Each `highlight` string within a `TailoredWorkEntry`/`TailoredProjectEntry` is
  **one atomic unit** the truthfulness gate turns into exactly one `Statement` — no
  re-parsing of prose into claims.
- `source_entry_id` on every tailored entry means each tailored bullet traces back
  to a specific master-profile entry, which both the gate (evidence resolution) and
  the future diff viewer (structural comparison) need.
- Rendering `TailoredContent` into plain text, a PDF, or ATS form fields is an
  explicit **downstream renderer concern**, not part of this model.
  `TailoredResume.rendered_text` may cache a rendering, but is documented as
  derived — never the source of truth.

## Alternatives considered

- **Free-text `content: str`.** Matches how a résumé is ultimately consumed by a
  human, but forces every consumer (gate, diff viewer) to re-parse prose into
  claims, with no guarantee the parse is stable. Rejected.
- **Markdown with embedded metadata** (e.g. HTML comments marking claim
  boundaries). Still requires parsing to extract statements; gains little over
  plain text while adding a bespoke format to maintain. Rejected.
- **A generic key-value "fields" bag** instead of a JSON-Resume-shaped structure.
  Loses the direct correspondence to `MasterProfile`'s sections, making
  `source_entry_id`-style traceability and diffing ad hoc rather than structural.
  Rejected in favor of mirroring the master profile's shape.

## Trade-offs

- **(+)** The gate verifies structure directly — one highlight, one `Statement`, no
  parsing. The diff viewer gets structural, section-by-section diffing for free.
  Every tailored claim is traceable to its source profile entry.
- **(−)** A renderer step is now a required part of producing user-facing output
  (plain text/PDF/ATS fields) — one more component to build (a later phase), though
  a small and clearly-scoped one. Structured content is marginally less flexible
  than prose for résumé styles that don't fit a JSON-Resume-like shape.

## Consequences

- `ResumeGenerator.tailor()` returns `TailoredResumeDraft` (structured, unverified);
  `TruthfulnessGate.verify()` consumes that draft directly, with no serialization
  round-trip through text.
- A renderer component (plain text / PDF / ATS form-field mapping) becomes an
  explicit, separately pluggable piece of Phase 7's application engine.
- The storage schema (Phase 5+) stores `TailoredContent` as structured data, not a
  text blob — this is the schema-leak this ADR exists to prevent.

## Future revisit criteria

Revisit if:

- A renderer needs to express content the structured model genuinely cannot (e.g. a
  free-form creative résumé format some ATS accept) and no reasonable extension of
  `TailoredContent` covers it.
- Structure proves too rigid across enough real-world résumé variety that it blocks
  legitimate tailoring rather than just constraining it usefully.
- JSON Resume's own schema evolves in a way `TailoredContent` should track more
  closely than it currently mirrors.
