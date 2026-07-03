# ADR-0031: QuestionAnswerer -- deterministic, template-based answering for the four custom-question categories

- **Status:** Accepted
- **Date:** 2026-07-03
- **References:** [ADR-0028](0028-browser-tier-dispatch-and-unsupported-field-refusal.md)
  (named this deferred future work, stated the EEOC no-guess-no-confirm
  absolute), [ADR-0030](0030-greenhouse-coverage-is-narrow.md)
  (re-prioritized this from "generalization nice-to-have" to "the actual
  gate on practical usefulness"), [ADR-0016](0016-truthfulness-gate-verification.md)
  (`ClaimVerdict`/`ClaimVerifier`, the entailment-judgment shape
  deliberately *not* reused for Category 4's similarity judgment),
  [ADR-0013](0013-held-candidate-mechanism.md) (precedent for a
  user-authored adversarial test matrix, not agent-generated)

## Context

ADR-0030's real-posting inspection found that an ordinary Greenhouse
posting requires Education, three legal work-authorization questions, a
full Voluntary Self-Identification section, and Veteran Status --
`_unhandled_required_fields` correctly refuses on all of them today, which
means most real postings end in a safe refusal rather than a completed
application. This ADR builds the deferred component that lets a defined,
narrow subset of that refusal set actually resolve, without weakening the
refusal for anything it can't answer.

## Decision

**Four categories, one shared component.** The question categories are
properties of *the question being asked*, not of which ATS platform is
asking it. `QuestionAnswerer` logic lives in a single new module,
`agents/apply/question_answerer.py`, not per-`FormFiller` -- splitting it
per platform would risk the EEOC absolute drifting or being silently
dropped in one platform's copy.

1. **EEOC/demographic self-identification -- an absolute.**
   `answer_eeoc_question(question_text, response)` takes **no
   `MasterProfile` parameter at all**. It only ever returns a human's own,
   unprompted `response` (or `None` for "declined," a complete, valid,
   terminal outcome). The absence of the parameter is itself the
   guarantee -- not "looked, found nothing, refused," but a structural
   impossibility of the lookup ever being attempted.

2. **Profile-groundable factual yes/no -- routed through a new, narrow
   `LegalStatusSection`.** Added to `MasterProfile`:
   `work_authorized_us: bool | None` and `requires_sponsorship: bool | None`.
   `None` means "not yet captured" -- never an implicit "no." Any code
   finding `None` raises `MissingLegalStatusFactError` rather than
   defaulting or inferring, the same "cannot proceed without this, ask the
   human" shape as `MissingSummaryError`. Deliberately narrow: exactly the
   two fields real observed questions have needed, not a general
   "arbitrary future facts" mechanism -- the same discipline behind
   `resolve_ats_kind` over a `CompanyRepository`, the flat `Settings`
   object, and `load_master_profile` as a plain function.

3. **Subjective/motivational freeform -- always human-authored.** There is
   no `answer_subjective_question` function anywhere in this module. The
   guarantee that no LLM ever drafts this content is structural (the
   capability was never built), not a runtime check that happens to
   prevent it every time.

4. **Structured-but-unmatchable dropdowns -- deterministic fuzzy matching,
   own confidence type.** `match_dropdown_option(profile_value, options)`
   returns `DropdownMatchResult` (`matched_option: str | None`,
   `similarity: float`, `candidate_options_considered: list[str]`) --
   deliberately not `ClaimVerdict`, since this is a similarity judgment,
   not a truth judgment, the same reasoning that kept `extraction_confidence`
   scoped inside `Provenance` rather than reusing an unrelated confidence
   type. Refuses (`matched_option=None`) when the best score is below
   `similarity_threshold` (default 0.7) **or** when the best and
   second-best scores are within 0.05 of each other (a near-tie among
   multiple plausible options). `AmbiguousDropdownMatchError` is a
   distinct exception type from `UnsupportedFormFieldsError`: the former
   means "I know this field and have a value, but can't confidently map it
   to any option this form actually offers"; the latter means "I don't
   know this field exists at all."

**Deterministic pattern/template matching, not a live model call --
deliberately, for now.** The investigation this ADR's pre-brief called for
(deterministic vs. LLM for categories 2 and 4) resolved differently than
the stated lean going in. EEOC self-identification questions follow
legally standardized (OFCCP-mandated) boilerplate wording across virtually
every US employer; common legal-status questions (work authorization,
sponsorship) are similarly conventional. That makes template/keyword
matching a real, defensible first approach for Category 2 as well as
Category 4 -- not the LLM-leaning approach originally anticipated. A
question whose phrasing matches no known template refuses rather than
guesses, and classification failure fails toward the safe category (EEOC
when genuinely ambiguous with a factual reading; Category 3's "human must
author this" as the default unmatched fallback) -- never toward a
confident wrong answer. A real, LLM-backed classifier remains a named,
deferred escalation if real-world use shows template-matching
insufficient.

**Composition order** (stated explicitly, not yet wired):
`BrowserApplicator` tries `FormFiller` first (known, declared fields) →
hands unhandled fields to `QuestionAnswerer` (four-category
classify/answer/pause/refuse) → hard refusal if neither resolves it. This
ADR builds `QuestionAnswerer` in isolation only -- wiring it into
`BrowserApplicator.submit()`'s live DOM flow is real, separate, explicitly
deferred future work, the same "prove the mechanism in isolation first,
wire it into the live flow as its own later step" sequencing this project
used for `ResumeTailoringPipeline` (ADR-0023) before `SubmissionPipeline`
(ADR-0024) wired a real `Applicator` in.

## Adversarial test matrix

Twenty cases across the four categories, drafted by the user -- not
generated by the agent implementing against them, the same discipline as
the truthfulness gate's 12-case matrix (ADR-0016) and the HN held-candidate
matrix (ADR-0013). Implemented in `tests/agents/test_question_answerer.py`
(18 tests; some matrix cases share a test). Four load-bearing cases were
independently verified by deliberately injecting the corresponding
violation, confirming the test caught it, then reverting -- never merged
on "this should work":

- **1d** (never even attempt a profile lookup for EEOC fields): injecting
  a `profile: MasterProfile | None` parameter into `answer_eeoc_question`
  made `test_case_1d_...` fail on `assert "profile" not in param_names`.
  Reverted.
- **2b** (negated-polarity questions): breaking the negation-inversion
  (`return fact` instead of `(not fact) if negated else fact`) made
  `test_case_2b_...` fail on the inverted assertion. Reverted.
- **3c** (restating true profile content into fresh prose is still
  unapproved generation): adding a spurious
  `if "experience" in question_text.lower(): return QuestionCategory.FACTUAL`
  inside `classify_question` made `test_case_3c_...` fail
  (`factual == subjective`). Reverted.
- **4c** (a close-but-wrong dropdown pick is worse than blank): lowering
  `match_dropdown_option`'s threshold and disabling the near-tie guard
  made `test_case_4c_...` fail (`'Computer Science' is None`
  assertion) -- proving both guards are independently load-bearing, since
  the first threshold-only injection attempt was still caught by the
  near-tie guard alone. Reverted.

## Named limitations (recorded honestly, not silently dropped)

- **Case 3a's scope boundary.** "How many years of Python experience do
  you have?" is profile-groundable in principle, but grounding it would
  require skill/work-history matching entirely outside `LegalStatusSection`'s
  scope -- a bigger, separate design question. This slice's Category 2 is
  scoped to `LegalStatusSection` only; the question currently falls to the
  safe `SUBJECTIVE` default (a human authors the answer -- never
  fabricates), which is safe but does not demonstrate the full
  Category-2-vs-3 boundary the matrix originally envisioned for this case.
- **Template-relaxation judgment call.** Case 1c's phrasing ("otherwise
  authorized to work in the US") omits "legally," which the original
  `_WORK_AUTH_TEMPLATE` required. Both templates were relaxed to make
  `legally\s+` optional. This is a judgment call about how much phrasing
  variance a "known template" can tolerate before it stops being
  deterministic-and-defensible; recorded here rather than left implicit in
  a regex diff.

## Alternatives considered

- **Reuse `ClaimVerdict` for Category 4.** Rejected per the pre-brief:
  dropdown-matching is a similarity judgment (does this string resemble
  that option), not a truth judgment (is this claim entailed by
  evidence) -- different kinds of uncertainty deserve different types,
  the same reasoning that kept `extraction_confidence` scoped inside
  `Provenance`.
- **Make `LegalStatusSection` a general `dict[str, Any]`-shaped fact
  store**, anticipating future question types. Rejected: this project has
  repeatedly chosen the concrete, narrow shape over a speculative general
  mechanism (`resolve_ats_kind`, the flat `Settings` object,
  `load_master_profile`) and generalizes only when a real second case
  appears.
- **Route Category 2 through an LLM call from the start**, per the
  pre-brief's stated lean. Rejected on investigation: the boilerplate is
  standardized enough that deterministic templates are defensible, and
  "prove the cheap thing first" is this project's established default
  (Category 4's dropdown matching, HN's heuristic-first design).
- **Wire `QuestionAnswerer` into `BrowserApplicator.submit()` in this same
  slice.** Rejected: the isolated-mechanism-first sequencing this project
  used for the resume-tailoring/submission pipeline split keeps this
  slice's surface area reviewable, and the live-DOM wiring is genuinely
  separate, larger work (pause-for-human semantics for three different
  categories, not just one).

## Trade-offs

- **(+)** All four category guarantees -- the EEOC absolute, the
  no-default-no-infer legal-status discipline, no-LLM-drafting for
  subjective content, and no-guess dropdown matching -- are structural,
  not conventions, and each was proven by deliberately breaking it and
  watching the test catch it.
- **(+)** `LegalStatusSection`'s backward compatibility is proven, not
  assumed: `default_factory=LegalStatusSection()` means existing profile
  JSON without a `legal_status` key loads cleanly, and
  `storage/profile.py`'s content-hash versioning picks it up automatically
  via `model_dump(mode="json", exclude={"version"})` with no additional
  code.
- **(−)** This slice answers nothing on a live page yet -- it is a proven
  mechanism in isolation, not new completion capability for
  `career-agent apply` until the deferred DOM-wiring step lands.
- **(−)** Category 2's real-world coverage is narrow (two fields); most of
  a real Greenhouse posting's custom-question surface (Education dropdowns
  via Category 4, EEOC via Category 1) is covered, but skill/experience
  questions are not yet properly classified, per the named Case 3a
  limitation.

## Consequences

- `src/career_agent/domain/models.py`: adds `LegalStatusSection` and
  `MasterProfile.legal_status`.
- `src/career_agent/agents/apply/question_answerer.py` (new): the four
  category functions/types described above.
- `tests/agents/test_question_answerer.py` (new): the 18-test
  implementation of the user's 20-case matrix.
- `src/career_agent/agents/apply/__init__.py`: package docstring updated
  to describe this module and its deliberately-deferred DOM-wiring
  boundary.
- The next real design pass on this system should wire `QuestionAnswerer`
  into `BrowserApplicator.submit()`'s live pause/resume flow, per the
  composition order stated above.

## Future revisit criteria

Revisit if:

- The DOM-wiring step is undertaken -- `BrowserApplicator.submit()` needs
  new pause/resume semantics for three different reasons (EEOC decline,
  legal-status capture, subjective authorship), not just the one challenge
  pause it already has (ADR-0020).
- Real-world use surfaces legal-status or EEOC question phrasing that no
  current template matches, at a rate that suggests template-matching is
  insufficient -- the named, deferred LLM-backed classifier escalation.
- A real profile-groundable-but-non-legal-status question (Case 3a's
  named limitation) becomes common enough in practice to justify widening
  Category 2's scope past `LegalStatusSection`.
- `LegalStatusSection` needs a third field -- per this ADR's narrow-scope
  decision, that should be added concretely when a real third question
  type appears, not preemptively generalized now.
