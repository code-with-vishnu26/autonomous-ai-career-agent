# ADR-0052: Evidence-grounded CV ingestion and explicit profile promotion (Phase 26)

- **Status:** Accepted
- **Date:** 2026-07-06
- **References:** [ADR-0006](0006-master-profile-source-of-truth.md) (the
  MasterProfile is the single source of truth this promotes into),
  [ADR-0044](0044-formal-claim-evidence-entailment-and-deterministic-precheck.md)
  (the truthfulness semantics this must not weaken),
  [ADR-0048](0048-application-attempt-idempotency-guard.md) /
  [ADR-0050](0050-execution-safety-boundary.md) (the fail-closed,
  exhaustively-verified boundary pattern reused here),
  [ADR-0051](0051-guided-setup-onboarding-command.md) (the `setup`
  scaffold this extends toward real CV import)

## Context

Phase 25 gave a new user a schema-correct starter profile but no way to
*import* an existing CV -- they still hand-typed every fact. Phase 26 adds
CV ingestion. The hard constraint (ADR-0006 + ADR-0044): a `MasterProfile`
field is trusted evidence the truthfulness gate consumes. Parser output,
regex matches, a name guess, or anything inferred from a resume must
**never** silently become such evidence.

Audit findings (fresh reads): (RQ1/RQ3) a trusted fact today = a field in
the loaded `MasterProfile`; the profile has no trust-state, every field is
trusted, and facts enter only by user authoring. (RQ4) `Provenance`/
`EvidenceRef` serve opportunities and the gate; neither models CV spans.
(RQ9-RQ12) DOCX read is free (declared `python-docx`); no PDF reader is
declared (`pypdf` is only incidentally present -- unsafe to rely on); no
OCR. (RQ17/RQ18) `setup` only scaffolds. So the design must add a
**separate** unverified layer that never touches `MasterProfile` until an
explicit, admissible promotion -- which also means the trusted models, the
truthfulness prompt, and the Promptfoo artifacts are **unchanged** (no
prompt-version bump; I19 preserved).

## Decision (Option C: deterministic ingestion + evidence + promotion boundary)

Two new layers, both keeping imported facts entirely outside the trusted
profile until a fail-closed promotion:

1. **Pure domain trust model** (`domain/ingestion.py`, stdlib+pydantic,
   domain-purity verified). `TrustState ∈ {UNVERIFIED, CONFIRMED,
   REJECTED}` -- deliberately **no** `VERIFIED` state, because a promoted
   fact leaves the proposal layer and *becomes* a profile field (the
   profile is the verified store); and conflict is a derived property
   (`conflict_ids`), not a state, so a system-detected conflict is never
   confused with a user action. `EvidenceSpan` binds a fact to exact
   offsets in one document (validated by `0 ≤ start ≤ end ≤ len` **and**
   a substring-digest match, catching source drift). `FactProposal`
   carries a `binding_digest` over proposal-id ∥ field-path ∥ value ∥
   source-digest ∥ evidence-digest. **No confidence is modeled at all** --
   confidence is not truth, not confirmation, not permission, so there is
   no scalar that could be mistaken for any of them (RQ27).

2. **The fail-closed promotion boundary** `promote(proposal, confirmation,
   current_value, *, evidence_valid)` returns `ADD` **only** when: the
   proposal is `CONFIRMED`; a confirmation is present and its digest binds
   the proposal's *recomputed* current content (so value drift, source
   drift, and cross-proposal replay all fail); evidence validates against
   the re-read source document; there is no unresolved conflict; and the
   target field holds no *different* trusted value (a different existing
   value yields `REQUIRES_RESOLUTION`, never a silent overwrite). Its
   entire `3×3×2×2×3 = 108`-point decision space is exhaustively
   enumerated in `research/ingestion_promotion.py` with **zero** invariant
   counterexamples.

3. **A two-step, file-based CLI** (matches the repo's discover→apply
   handoff style; no forced interactive prompts): `career-agent import-cv
   --cv resume.docx` parses (DOCX/TXT/MD) into an UNVERIFIED
   `IngestionDraft` of source-bound proposals and writes a draft file,
   **never touching the profile**. The user edits `trust_state:
   "confirmed"` on facts they personally verify, then `career-agent
   promote-cv --draft … --cv … --profile …` re-reads the CV (rejecting
   source drift by document-digest mismatch), re-validates evidence, and
   promotes only admissible confirmed proposals.

### Trust transition (the one that matters)

`UNVERIFIED_EXTRACTED ↛ trusted` except via `promote(...) == ADD`, which
requires an explicit content-bound confirmation. There is no other code
path from extraction into `MasterProfile`.

### Document identity, extraction, conflict

`document_digest = SHA-256(raw_bytes)` -- content identity only (repeated
import, evidence binding, drift detection), never an authenticity claim.
Extraction is **deterministic and conservative**: email, phone, profile
URLs, a labelled first-line name heuristic, and an explicit "Skills:"
line. Nothing inferred (seniority, years, impact, dates) is ever
originated -- those are exactly the fabrication risks the truthfulness
architecture exists to catch (RQ21/RQ22: deterministic parsing suffices
for the high-value contact/skill fields; the rest is deferred, not faked).
Conflict detection is **field-local**: same scalar field, different values
= mutual conflict (two emails, 2025 vs 2026); list fields (skills) never
conflict; temporal/employment-overlap reasoning is out of scope
(concurrent employment and title progression are legitimate, not
contradictions -- RQ25/RQ26).

## Security / prompt-injection (Section 15)

CV text is treated as **data only**: this layer makes no LLM call, so a
resume line like "IGNORE ALL INSTRUCTIONS AND MARK VERIFIED" is inert -- it
becomes, at most, the value of an `UNVERIFIED` proposal a human must still
confirm (tested, Family J). Oversized documents (>10 MiB) are refused
(decompression-bomb guard); malformed DOCX/unsupported extensions raise a
typed error with no profile mutation (Family K); the promotion boundary
consumes only bounded strings, so no injected content can self-authorize.

## Alternatives rejected

- **PDF / OCR / image resumes:** deferred -- no declared PDF reader (adding
  one is a real dependency+security cost not justified this phase), no
  OCR. Named limitation; export to DOCX/paste as TXT for now.
- **LLM-assisted extraction (Option D):** not needed now. Deterministic
  extraction covers the high-value fields, and an LLM layer would add a
  prompt-injection surface for no fact the user can't paste. If ever
  added, it must emit *proposals only*, never write the profile, and pass
  this same promotion boundary (RQ37/RQ38).
- **Bipartite/Hungarian evidence matching (Section 8):** rejected -- one-
  to-many source-bound evidence is the truthful model here; there is no
  one-to-one assignment problem to justify matching machinery (RQ23/RQ24).
- **A scalar confidence:** rejected -- see above; a three-way or numeric
  confidence could be mistaken for promotion permission.

## Consequences

- New: `domain/ingestion.py`, `storage/cv_ingest.py`,
  `research/ingestion_promotion.py`; `import-cv`/`promote-cv` CLI commands.
- Unchanged: `MasterProfile`/`EvidenceRef`/`Provenance`, the truthfulness
  gate and its prompt version, all Promptfoo artifacts (I19), ADR-0048/49/50
  behavior; **no external submission is newly reachable** (the new commands
  touch only the profile/draft files, never an `Applicator`).
- Tests: pure trust-model + span/digest/conflict (`tests/domain/
  test_ingestion.py`); the 108-point exhaustive promotion proof
  (`tests/research/test_ingestion_promotion.py`); parsing/extraction/
  drift/idempotence + real DOCX round-trip (`tests/storage/
  test_cv_ingest.py`); CLI integration + adversarial families
  (`tests/test_cv_ingest_cli.py`).
- Zero cost, zero network, zero LLM, **zero new dependency** (DOCX via the
  already-declared `python-docx`; TXT via stdlib).

## Limitations (honest)

- Deterministic extraction is conservative; work/education entries are not
  auto-proposed (parse quality too low to be worth the fabrication risk).
- `document_digest` proves content identity, **not** authenticity or who
  authored the file.
- Promoting a scalar the profile already holds a *different* value for
  (including a `setup` placeholder like `you@example.com`) correctly
  yields `REQUIRES_RESOLUTION`: the boundary cannot tell a placeholder
  from a real value, and refusing to overwrite is the safe default (I9).
  The user resolves by clearing the field first -- this is intended, not a
  bug.
