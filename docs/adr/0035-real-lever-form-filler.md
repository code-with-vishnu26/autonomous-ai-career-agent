# ADR-0035: Real LeverFormFiller — single-name fill, required file upload, hCaptcha through existing pause/resume

- **Status:** Accepted
- **Date:** 2026-07-04
- **References:** [ADR-0029](0029-per-filler-challenge-and-submit-selectors.md)
  (the human dev-tools inspection whose recorded evidence this ADR builds
  on), [ADR-0033](0033-resume-file-generation.md) (the DOCX artifact this
  filler attaches), [ADR-0020](0020-browser-tier-session-and-pause.md)
  (the pause/resume machinery hCaptcha flows through unchanged)

## Context

`LeverFormFiller` has been an explicit stub since ADR-0028 for two named
reasons: unverified selectors, and no resume *file* artifact anywhere in
the domain model. Both blockers are now closed: ADR-0029 recorded the
real DOM evidence from a live jobs.lever.co inspection, and ADR-0033
built the canonical DOCX artifact. The standing master brief names this
Phase 11 with the evidence summary: single `name='name'` field,
`name='email'`, no `id` attributes, resume file-upload-only ("Attach
Resume/CV", required), hCaptcha present.

## Decision

- **Selectors from recorded evidence, not guesses:**
  `[name='name']`/`[name='email']`/`[name='resume']`;
  `challenge_selector="#h-captcha"`; `submit_selector="#btn-submit"`.
  Live validation against a real posting on the user's machine remains
  the final pre-submission check (offline-fixture-first discipline) — the
  fixture (`tests/fixtures/lever/apply_form_real.html`) carries every
  load-bearing recorded property, not real Lever markup.
- **The full name is written unsplit to the single name field** — Lever's
  one-field shape means the `_split_name` heuristic's documented
  imprecision (ADR-0027) never applies here at all.
- **The resume is attached via `set_input_files` with the application's
  own DOCX artifact** — the canonical, deterministic, content-addressed
  file from ADR-0033, reached through `TailoredResume.artifacts` with no
  new lookup machinery. The test suite verifies the *live input's real
  FileList* contains exactly that artifact's filename — the attach is
  proven against DOM state, not inferred from the call having happened.
- **`MissingResumeArtifactError` (new, typed):** raised before touching
  the page when the application carries no DOCX artifact or the recorded
  file is gone from disk. Lever has no manual-text path, so nothing to
  upload means no honest submission — a precondition failure named
  plainly (the fix: run with `artifacts_dir` set), never a silent skip of
  a required field.
- **hCaptcha flows through ADR-0020's machinery unchanged**: pause on
  visibility, refuse to resume while still visible, complete only after a
  human clears it. No solving services, no bypass, ever — re-verified
  end-to-end against the real-shape fixture.
- The old stub-reached-through-the-real-flow test is superseded by the
  same proof shape applied to the new precondition:
  `MissingResumeArtifactError` genuinely raised through real
  `prepare()`/`submit()`. `AshbyFormFiller` remains a stub (Phase 18,
  blocked on human DOM inspection).

## Load-bearing verification (by injection)

1. **Silent-skip of the required upload** (no-artifact check removed,
   upload made conditional): caught — the refusal test failed loudly.
   Reverted.
2. **Wrong file attached** (a copied `rogue.docx` instead of the
   application's own artifact): caught by the FileList filename-identity
   assertion (`rogue.docx != resume-{id}-{hash}.docx`). Reverted;
   byte-identical restore confirmed via diff against the pre-injection
   copy; full suite/ruff/import-linter clean after.

## Alternatives considered

- **Wait for a second live-posting inspection before building.**
  Rejected by the standing brief: the evidence is recorded, the fixture
  encodes it, and live validation on the user's machine is the named
  final check either way. Staying a stub blocks the only real submission
  path (Tier 1 is dead, ADR-0027) for no added safety.
- **Fall back to `rendered_text` in some hidden field when no artifact
  exists.** Rejected: Lever has no text path; inventing one would be
  submitting around a required field.

## Trade-offs

- **(+)** The only ATS this project can really submit through gains a
  second real platform, with the file-attach step proven against real
  DOM state.
- **(−)** `#btn-submit`/`#h-captcha`/`[name='resume']` are single-
  inspection evidence; Lever forms are org-configurable, so a posting
  with different markup will fail loudly (Playwright timeout / unhandled-
  field refusal), not silently — but it will fail. Live validation
  remains required before first real use.

## Consequences

- `agents/apply/form_fillers.py`: real `LeverFormFiller`,
  `MissingResumeArtifactError`.
- `tests/fixtures/lever/apply_form_real.html` (new); Phase 11 test
  section in `tests/agents/test_browser_applicator.py`.

## Future revisit criteria

- The user's live validation on a real posting finds different markup —
  update selectors from that evidence, same as ADR-0029.
- A Lever posting exposes required custom/EEOC questions — they flow into
  the existing Phase A manifest (ADR-0032) automatically; verify against
  a real posting when encountered.
- Ashby's inspection lands (Phase 18) — same build pattern applies.
