# ADR-0033: Resume file generation — deterministic, ATS-safe DOCX/PDF traceable to gated content

- **Status:** Accepted
- **Date:** 2026-07-04
- **References:** [ADR-0025](0025-resume-renderer.md) (the plain-text
  renderer whose placement and never-silently-drop discipline this ADR
  extends to files), [ADR-0016](0016-truthfulness-gate-verification.md)
  ("Case #6 revisited": dates reach the resume from the profile, never
  from a generator-writable field — the pattern Education now follows),
  [ADR-0029](0029-per-filler-challenge-and-submit-selectors.md) (Lever's
  file-upload-only resume field, the concrete consumer this unblocks)

## Context

Phase 11 (real `LeverFormFiller`) is blocked on a real resume *file*:
Lever's confirmed DOM has a required "Attach Resume/CV" upload and no
text path. More broadly, a DOCX/PDF is what a company actually receives —
full-intensity review applies. This is also the project's first binary
artifact, which raises a traceability question text never had: a file on
disk is opaque, so its link to the gated content that produced it must be
carried as data.

## Decision

### Education is sourced read-only from `MasterProfile` (Option (a), authoritative)

Education is a verified profile fact, not content to tailor. It is
rendered verbatim from `profile.education` (plain reverse-chronological
ordering only — no semantic reordering, rewording, or optimization) and
deliberately does **not** exist on `TailoredContent` or `DraftedTailoring`
at all. The guarantee is structural, the same shape as
`TailoredWorkEntry` having no date field: no generated type carries
education, so no drafter/generator output can override or fabricate it —
there is nowhere to put it. Tested via `model_fields` assertions, not
just behavior. The truthfulness gate's surface is unchanged.

Company names joined Education in the read-only-from-profile path:
`resolve_work_entry` (new, in `domain/rendering.py`) returns the full
linked `WorkEntry`; `resolve_work_dates` now delegates to it, so dates
and company names come from one lookup with one loud-`KeyError`
discipline.

### `ResumeArtifact`: content-addressed, never silently overwritten

New domain model: `resume_id`, `profile_version`, `format`
(`docx`/`pdf`), `path`, `content_hash` (sha256 of the file bytes). The
hash's first 12 chars are embedded in the filename
(`resume-{resume_id}-{hash12}.docx`), which makes never-overwrite true
**by construction** rather than by a check: different content cannot
share a name; identical content maps to the identical name (idempotent
regeneration, not a duplicate).

`TailoredResume.artifacts` is a derived cache with exactly
`rendered_text`'s status (ADR-0025): populated by
`ResumeTailoringPipeline` for approved drafts only — the one place
content and profile are both in scope — so no applicator ever gains a
profile or renderer dependency; Phase 11's Lever filler will read the
path straight off the `SubmittableApplication` it already receives.
File generation is opt-in at the composition root
(`artifacts_dir: Path | None`, wired from `Settings.artifacts_dir`,
default `data/artifacts`) — tests and scoring-only flows never touch the
filesystem.

### DOCX determinism required zip-timestamp normalization (empirical finding)

A DOCX is a zip; python-docx stamps entries with the wall clock. Verified
in this environment: two identical renders straddling a second boundary
hash differently — which would break content addressing (same content,
two names). `_normalize_zip_timestamps` rewrites the archive with a fixed
epoch and sorted entries, making DOCX bytes a pure function of
(content, profile); the normalized file remains valid and
LibreOffice-convertible (verified). The PDF is a **derived view** and is
NOT byte-reproducible (LibreOffice embeds a creation timestamp); its hash
still provides traceability and collision-safety, but the DOCX is the
canonical, deterministic artifact — stated plainly rather than rounded up
to "everything is deterministic."

### PDF via LibreOffice headless, availability checked at runtime, typed refusal

DOCX-first via python-docx, converted with
`soffice --headless --convert-to pdf`. The pre-brief's environment check
found a real trap: this sandbox shipped `soffice` with only
`libreoffice-core` — the binary existed but could not load a DOCX until
`libreoffice-writer` was installed ("source file could not be loaded").
So converter availability is a runtime check, never an assumption:
missing/failing conversion raises the typed
`PdfConversionUnavailableError`. In the pipeline, a conversion failure
does not fail the run — the DOCX (canonical, and the format Lever
accepts) is already on disk, and the PDF's absence is structurally
visible (no `format="pdf"` entry in `artifacts`) plus a logged warning,
not swallowed into a boolean nobody checks. ReportLab stays a named,
unbuilt fallback (revisit criterion: a real environment with no
LibreOffice at all).

### The locked ATS-safe layout spec

Single column; no tables, text boxes, images, or headers/footers (contact
identity in the body); exactly the five standard headings ("Summary",
"Work Experience", "Education", "Skills", "Projects"), with an empty
section's heading omitted entirely; Calibri 11pt via the Normal style;
reverse-chronological work and education. Verified by tests that read the
generated file back through python-docx — never trusted from the writer's
intent. A required field with unsafe constructs fails generation loudly
(`_forbid_unsafe_constructs`, run immediately **before save** — see
below). The renderer independently re-verifies every `source_entry_id` it
renders (loud `KeyError`, never a silently dropped entry), the same
never-trust-upstream discipline as the text renderer.

## Injection verification (three passes, two real gaps found)

1. **Table injected into the build path.** Caught by the file-reading
   layout test — but the injection also exposed that
   `_forbid_unsafe_constructs` originally ran on the *fresh* document,
   before content was added, so the runtime check itself never saw the
   table. Fixed: the check now runs immediately before save, and a
   re-injection confirmed the runtime check itself now fires
   (`ValueError`), independent of the test. Reverted.
2. **Content-hash filename replaced with a fixed name** (silent-overwrite
   bug). Caught by two tests: the old file's bytes were clobbered
   (`test_changed_content_gets_a_new_file...`) and traceability broke
   (`test_artifact_records_trace_back...`). Reverted.
3. **Normalization step skipped.** NOT caught on the first attempt — a
   genuine test weakness: ZIP DOS timestamps have 2-second granularity,
   and the test's ~1s sleep could land both renders in the same bucket,
   passing by luck. Test strengthened to sleep past the 2s boundary;
   re-injection then failed the test as intended. Reverted. Recorded
   because an injection that *doesn't* fail is exactly the signal the
   discipline exists to produce.

## Alternatives considered

- **Add education to `TailoredContent`.** Rejected (authoritative
  decision): it would turn a verified profile fact into generated content,
  expanding the truthfulness gate's surface for zero benefit — education
  is not something this project tailors.
- **ReportLab-first PDF.** Rejected for now: LibreOffice conversion from
  the canonical DOCX gives one layout source of truth; ReportLab would
  mean maintaining a second, parallel layout implementation. Named
  fallback only.
- **Overwrite-with-backup or timestamped filenames.** Rejected: content
  addressing makes the overwrite question structurally moot and gives
  idempotent regeneration for free; timestamps would create duplicate
  files for identical content.
- **Store artifacts on `Application` instead of `TailoredResume`.**
  Rejected: the artifact renders the *resume*, and `TailoredResume`
  already owns the analogous derived cache (`rendered_text`); an
  `Application` reaches it through its resume exactly as it reaches
  `rendered_text` today.

## Trade-offs

- **(+)** Every file a company could receive is traceable to the exact
  gated content and profile version that produced it, deterministic
  (DOCX), and structurally incapable of silently replacing a previously
  generated file.
- **(+)** Education gains the strongest guarantee available — structural
  absence from every generated type — at zero gate cost.
- **(−)** PDF bytes are not reproducible run-to-run (LibreOffice
  CreationDate); accepted and documented rather than solved with PDF
  post-processing this slice.
- **(−)** PDF availability depends on `libreoffice-writer` being
  installed; environments without it produce DOCX-only artifact lists.
- **(−)** The `.building-*/.normalized-*` temp files briefly exist in the
  artifacts dir during generation; crash cleanup is not implemented this
  slice (stale temp files are inert and visibly named).

## Consequences

- `domain/models.py`: `ResumeArtifact`; `TailoredResume.artifacts`.
- `domain/rendering.py`: `resolve_work_entry`; `resolve_work_dates`
  delegates.
- `agents/resume/file_renderer.py` (new): `render_resume_docx`,
  `convert_to_pdf`, `PdfConversionUnavailableError`, the layout builder,
  zip normalization.
- `agents/resume/pipeline.py`: optional `artifacts_dir`; artifacts for
  approved drafts only.
- `core/config.py`: `Settings.artifacts_dir`.
- `cli.py`: wires `Settings.artifacts_dir`; prints written artifact paths.
- `pyproject.toml`/`requirements.txt`: `python-docx>=1.1`.
- Phase 11 (Lever) is unblocked: `set_input_files` gets a real, traceable
  DOCX path from the application it already holds.

## Future revisit criteria

Revisit if:

- A real environment (the user's machine) lacks LibreOffice entirely —
  the ReportLab fallback becomes real work.
- Phase 10's ATS gate wants to score the rendered *file* rather than the
  content — the format-safety score is auto-100 by construction for this
  renderer, but scoring arbitrary external files would need real checks.
- A real ATS is found to mis-parse this layout — the spec is locked
  against known parser behavior, not proven against every parser.
- PDF reproducibility starts to matter (e.g. artifact diffing) —
  LibreOffice's CreationDate can be stripped post-conversion.
