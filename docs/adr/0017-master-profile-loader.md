# ADR-0017: Master profile loader — required ids, scoped content hash, plain function

- **Status:** Accepted
- **Date:** 2026-07-02
- **References:** [ADR-0006](0006-json-resume-master-profile.md) (JSON Resume
  as the single source of truth), [ADR-0012](0012-opportunity-provenance-and-confidence.md)
  (the confidence/id discipline this ADR extends), [ADR-0016](0016-truthfulness-gate-verification.md)
  (`EvidenceRef`'s dependence on stable entry ids and a stable profile version)

## Context

`MasterProfile` and its entry types (`WorkEntry`, `SkillEntry`, `EducationEntry`,
`ProjectEntry`) have existed since Phase 2. Every entry requires an `id`,
"assigned once and never reused" — `EvidenceRef` and the entire Phase 5
truthfulness gate depend on that being true. `MasterProfile.version` is
documented as "a content hash of the full document." Neither has an
implementation: nothing yet turns a real JSON Resume file on the user's disk
into a validated `MasterProfile`.

## Problem

How does a real JSON Resume file — a format with no native per-entry `id` —
become a `MasterProfile` whose ids are actually stable, whose `version` is
actually a deterministic content hash, and what shape should the loader
itself take?

## Decision

### Ids: required and rejected-if-missing, never inferred (`storage/profile.py::_validate_ids`)

JSON Resume has no `id` field on `work`/`education`/`skills`/`projects`
entries. Considered three ways to bridge that: derive an id from entry
content (rejected — the id would silently change the moment the user edits a
title or date, exactly the failure mode ADR-0012's content-addressed
immutable-snapshot design exists to prevent, and two entries could collide);
a separate sidecar id-mapping file (rejected — relocates the sync problem to
a second file that can drift out of sync with the profile instead of
eliminating it); requiring an explicit `id` per entry and **rejecting** the
file if one is missing, rather than inferring or silently writing one back
(**chosen**). This is the only option that doesn't either break the
never-reused guarantee or introduce a second source of truth.

Uniqueness is enforced **globally across all four sections**, not just
per-section — a work entry and a project entry accidentally sharing an id is
exactly the resolution ambiguity the guarantee exists to prevent, and
checking only within a section would miss it.

The missing-id error message is deliberately actionable (names the section
and index, gives an example) rather than a raw Pydantic "field required" —
this is expected to be the first user-facing friction point in the whole
system, since it fires on someone's existing, unmodified resume.

### `version`: a deterministic hash over exactly what `MasterProfile` models

Computed from the already-validated `MasterProfile`'s own canonical dump
(`model_dump(mode="json", exclude={"version"})`, sorted keys, compact
separators, SHA-256), **not** from the raw file text and **not** from the
whole raw JSON Resume document. Two reasons: hashing the raw text would make
the version sensitive to incidental formatting (key order, whitespace) that
carries no semantic difference; hashing the whole document would make
`version` bump when a JSON Resume section this loader doesn't even import
changes (see below), producing a false-positive staleness signal — every
stored `EvidenceRef` referencing unrelated, still-true facts would look stale
and force re-verification for no real reason. Tested directly: an added
`awards` section or a changed structured `basics.location` object leaves
`version` unchanged; a changed work highlight changes it.

### Out of scope, named not silently dropped (Career Page Finder pattern)

Not imported at all: `awards`, `publications`, `languages`, `interests`,
`references`, `volunteer`, and the structured sub-objects `basics.location`
(JSON Resume's `{address, city, region, ...}` object — only a plain string
location is imported) and `basics.profiles`. None of these are needed for
what Phases 6–8 actually do (ground claims, tailor resumes, gate
truthfulness). Revisit if a future phase needs to ground a claim in one of
them.

### A plain function, not a `Protocol`

`load_master_profile(path: Path) -> MasterProfile`. Every existing `Protocol`
in this system (`OpportunitySource`, `SearchProvider`, `ATSAdapter`) earns its
abstraction because there are genuinely multiple real implementations today.
There is exactly one master profile format and no plausible second
implementation on the roadmap — a `Protocol` with one implementer would be
speculative generality, the same mistake this project has avoided everywhere
else. If a second profile source appears (e.g. a web form that builds a
profile without a file), that is the moment to extract a `Protocol`, not
before.

### Other validation errors: surfaced from Pydantic directly, not re-wrapped

Only the id checks get a custom, actionable message. A missing required
field (e.g. no `startDate` on a work entry) or a malformed date raises the
underlying `pydantic.ValidationError` unwrapped — re-wrapping every possible
validation failure with custom prose was judged not worth the effort
relative to the one friction point (missing ids) that is expected to be
common and confusing on a first, unmodified real-world file.

## Alternatives considered

- **Content-derived ids.** Rejected: breaks the never-reused guarantee the
  moment a title or date is edited.
- **Sidecar id-mapping file.** Rejected: a second source of truth that can
  desync from the profile is a new failure mode, not a smaller one.
- **Silently assigning and writing back missing ids.** Rejected: the same
  "loud, required, once" discipline as `provenance` (ADR-0012) and
  `canonical_company` (ADR-0014) — force correctness at the boundary rather
  than infer it and hope.
- **Hashing the whole raw file for `version`.** Rejected: makes `version`
  sensitive to both incidental formatting and unmodeled-section edits,
  producing false-positive `EvidenceRef` staleness.
- **A `ProfileRepository`/`ProfileSource` `Protocol`.** Rejected as premature
  abstraction: one implementation, no second one in view.

## Trade-offs

- **(+)** The `EvidenceRef`/never-reused-id guarantee is honored by
  construction, not by convention; `version` only moves when a grounding fact
  actually changed; the loader is honest about what it does and doesn't
  import, tracked rather than silently dropped.
- **(−)** Every user must add an `id` to each entry of their existing resume
  before it loads — one-time friction, accepted as trivial next to what it
  protects. JSON Resume sections this loader ignores are simply unusable for
  grounding until a future phase adds them.

## Consequences

- `storage/profile.py` is new: `load_master_profile`, `ProfileValidationError`,
  and the JSON-Resume-camelCase-to-domain-snake_case mapping functions.
- No change to `domain/models.py` — `MasterProfile` and its entry types were
  already correctly shaped for this; the loader is where the id/version
  contracts they always implied actually get enforced.
- Phase 7/8's `ResumeGenerator` and any future profile-editing tooling must
  go through this loader (or honor the same id/version contract) rather than
  constructing `MasterProfile` ad hoc.

## Future revisit criteria

Revisit if:

- A second real profile source appears (e.g. a web form), at which point
  `load_master_profile` should be extracted behind a `Protocol`.
- Any of the currently-unimported JSON Resume sections (`awards`,
  `publications`, `languages`, `interests`, `references`, `volunteer`,
  structured `basics.location`/`basics.profiles`) become needed for grounding
  a real claim type.
- The one-time id-migration friction proves too high in practice and a
  supervised (not silent) one-time migration tool is warranted.
