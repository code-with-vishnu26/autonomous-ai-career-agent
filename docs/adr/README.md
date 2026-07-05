# Architecture Decision Records (ADRs)

This directory records the significant architectural decisions made on this
project, and the context and consequences behind them. ADRs are immutable once
accepted: if a decision changes, we add a new ADR that supersedes the old one
rather than editing history.

[ADR-0000](0000-project-philosophy.md) is the **root**: it states the mission,
goals, non-goals, engineering principles, and golden rules. Every other ADR is
made in service of it; when two decisions conflict, the one more aligned with
ADR-0000 wins.

## Format

Each ADR is a numbered Markdown file: `NNNN-short-title.md`, using the template
below. Every ADR **must** end with *Future revisit criteria* so decisions stay
open to change instead of freezing forever.

```markdown
# ADR-NNNN: Title

- **Status:** Proposed | Accepted | Superseded by ADR-XXXX
- **Date:** YYYY-MM-DD
- **References:** (optional) related ADRs

## Context
What is the situation and the forces at play?

## Problem
The specific question this ADR answers.

## Decision
What we decided to do.

## Alternatives considered
What else we weighed and why we didn't choose it.

## Trade-offs
The costs we accept in exchange for the benefits.

## Consequences
The results — positive, negative, and neutral — of the decision.

## Future revisit criteria
The conditions under which we should reopen this decision.
```

## Index

| ADR | Title | Status |
|-----|-------|--------|
| [0000](0000-project-philosophy.md) | Project philosophy (mission, goals, non-goals, golden rules) | Accepted |
| [0001](0001-agent-oriented-architecture.md) | Agent-oriented architecture (not a fixed pipeline) | Accepted |
| [0002](0002-search-provider-abstraction.md) | Search provider abstraction (capabilities + health-based ranking) | Accepted |
| [0003](0003-truthfulness-gate.md) | Truthfulness gate (per-statement evidence, confidence, explainability) | Accepted |
| [0004](0004-plugin-architecture.md) | Plugin architecture (everything external is replaceable) | Accepted |
| [0005](0005-event-bus.md) | Event bus (loose coupling, no direct agent calls) | Accepted |
| [0006](0006-json-resume-master-profile.md) | JSON Resume master profile (single source of truth) | Accepted |
| [0007](0007-planner-agent.md) | Planner Agent (coordinator only; Decide as swappable step) | Accepted |
| [0008](0008-human-in-the-loop.md) | Human-in-the-loop application (pause, never bypass) | Accepted |
| [0009](0009-learning-engine.md) | Learning engine (improve from real outcomes) | Accepted |
| [0010](0010-hybrid-application-strategy.md) | Hybrid (tiered) application strategy (API → browser → email) | Accepted |
| [0011](0011-structured-tailored-content.md) | Structured tailored resume content (not free text) | Accepted |
| [0012](0012-opportunity-provenance-and-confidence.md) | Opportunity provenance + extraction confidence (honest uncertainty) | Accepted |
| [0013](0013-held-candidate-mechanism.md) | Held-candidate mechanism for freeform extraction sources (visible discard pile) | Accepted |
| [0014](0014-cross-source-opportunity-identity.md) | Cross-source opportunity identity: two-key dedup + canonical company | Accepted |
| [0015](0015-web-search-classification.md) | Web-search results are classified, not trusted (applies ADR-0013 to search) | Accepted |
| [0016](0016-truthfulness-gate-verification.md) | Truthfulness gate verification: entailment, categories, and the ClaimVerifier harness | Accepted |
| [0017](0017-master-profile-loader.md) | Master profile loader: required ids, scoped content hash, plain function not a Protocol | Accepted |
| [0018](0018-submission-safety.md) | Submission safety: structural approval (SubmittableApplication), confirmation-token binding, verifier isolation | Accepted |
| [0019](0019-ats-kind-resolution-and-tier-fallback.md) | ATS-kind resolution (reused ADR-0015 pattern-match, no new repository) and no cross-tier auto-retry | Accepted |
| [0020](0020-browser-tier-session-and-pause.md) | Browser-tier session encryption (OS-keychain-backed, fail-closed) and the token-bound pause/resume guarantee, proven against real Playwright | Accepted |
| [0021](0021-email-tier-draft-only.md) | Email tier is draft-only: EmailDraftSink has no send method, submit() never claims ApplicationSubmitted | Accepted |
| [0022](0022-resume-generator.md) | ResumeGenerator: structural summary (no drafter write access), narrow ContentDrafter port not permanently cascade-exempt, no self-verification | Accepted |
| [0023](0023-resume-tailoring-pipeline.md) | Resume-tailoring pipeline: composition stops at SubmittableApplication (no Applicator call), new "rejected" status distinct from "failed", reuses dormant ResumeTailored/TruthfulnessRejected events | Accepted |
| [0024](0024-real-confirmation-and-submission-wiring.md) | Real human confirmation (cli.confirm_submission, no default-to-yes) and single-tier SubmissionPipeline; multi-tier selection confirmed unbuilt, deferred | Accepted |
| [0025](0025-resume-renderer.md) | Resume renderer: computed once at pipeline resume-creation time (no Applicator changes needed), raises loudly rather than silently dropping an unresolvable entry | Accepted |
| [0026](0026-real-apply-command-and-promptfoo-enforcement.md) | Real `career-agent apply` command: `--opportunity-file` handoff, promptfoo pass positively verified against a results artifact (not a claimed flag) before AnthropicClaimVerifier is constructed, stops at confirmation (no real ATSAdapter yet) | Accepted |
| [0027](0027-applicant-identity-snapshot.md) | Applicant identity snapshot: Application.applicant (required, frozen BasicsSection) prevents prepare/submit identity drift; BrowserApplicator._fill_form now uses real data with a documented, known-imprecise name split; Tier 1 direct-API submission confirmed dead across Greenhouse/Lever/Ashby | Accepted |
| [0028](0028-browser-tier-dispatch-and-unsupported-field-refusal.md) | Browser-tier per-ATS FormFiller dispatch (resolve_ats_kind, Lever/Ashby stubbed pending human verification); live-DOM-verified refusal of any required field no filler knows how to fill; custom-questions/EEOC answering deferred to its own ADR, with an absolute no-guess-no-confirm rule stated now for EEOC fields specifically | Accepted |
| [0029](0029-per-filler-challenge-and-submit-selectors.md) | Per-FormFiller challenge_selector/submit_selector (real hCaptcha markup found on a live Lever posting would never have matched Greenhouse-hardcoded literals) and name-based field-selector matching (real Lever fields have no id attribute); LeverFormFiller stays a stub since the resume field's real interaction shape is still unconfirmed | Accepted |
| [0030](0030-greenhouse-coverage-is-narrow.md) | Greenhouse's resume_text DOM-confirmed as a real "Enter manually" option (exact toggle interaction still unconfirmed); corrects the record that an ordinary real Greenhouse posting requires far more than identity+resume (Education, legal-status, full Voluntary Self-ID, Veteran Status), so "Tier 2 works" means narrow completion + correct refusal on most postings, not broad completion -- re-prioritizes the deferred custom-questions/EEOC design pass accordingly | Accepted |
| [0031](0031-question-answerer.md) | QuestionAnswerer: four custom-question categories (EEOC absolute with no MasterProfile access at all, LegalStatusSection-backed factual yes/no with None-means-uncaptured, always-human-authored subjective, deterministic no-guess dropdown matching with its own DropdownMatchResult type); deterministic template matching over an LLM call for all categories; user-authored 20-case adversarial matrix, four load-bearing cases independently verified by injection; DOM-wiring into BrowserApplicator deliberately deferred | Accepted |
| [0032](0032-question-answerer-wiring.md) | Wires QuestionAnswerer into BrowserApplicator's live pause/resume flow: two sequential pause phases (pre-click fields-need-human-input, post-click challenge), the human fills every manifested field directly on the visible page rather than through a typed answer payload (EEOC data never becomes a value this process holds), Application.legal_status extends the applicant frozen-snapshot precedent one field wider with zero new MasterProfile-storage dependency, _PausedSession's reason discriminator proven load-bearing by injection | Accepted |
| [0033](0033-resume-file-generation.md) | Resume file generation: deterministic ATS-safe DOCX (zip-timestamp-normalized; raw python-docx is not cross-second deterministic, verified) + LibreOffice-headless PDF as a derived non-reproducible view with a typed runtime-availability refusal; Education sourced read-only from MasterProfile, structurally absent from every generated type (authoritative Option (a)); ResumeArtifact content-hash-addressed filenames make silent overwrite impossible by construction; injection pass found and fixed the check-before-content gap and a 2s-ZIP-granularity test weakness | Accepted |
| [0034](0034-ats-score-gate.md) | ATS score gate: deterministic curated-taxonomy scoring is the entire pass/fail authority (spaCy model rejected -- artifact-dependent determinism is not determinism); passed computed in the report type itself (threshold + hard-format override); advisory semantic layer prunes the gap report only, every claim verbatim-verified, deliberately NOT cost-cascade-exempt (gates nothing, reasoning recorded); retailor loop with truthfulness-gate-before-every-score, GENUINE gaps structurally unreachable by the drafter (AtsGapReport has no field for them), convergence detection, trajectory-carrying typed refusal; reviewer-drafted 14-case matrix, four load-bearing cases injection-verified | Accepted |
| [0035](0035-real-lever-form-filler.md) | Real LeverFormFiller from ADR-0029's recorded live-DOM evidence: single unsplit full-name field, required file upload satisfied by attaching the application's own ADR-0033 DOCX artifact via set_input_files (FileList-verified, injection-proven against a wrong-file swap), typed MissingResumeArtifactError precondition refusal, hCaptcha through ADR-0020's pause/resume unchanged -- live validation on the user's machine stays the named final check | Accepted |
| [0036](0036-worldwide-job-board-sources.md) | Eight Tier A worldwide job-board sources (Adzuna/Reed/USAJobs/Arbeitnow/TheMuse/Remotive/RemoteOK/Jooble) behind the unchanged OpportunitySource Protocol with shared normalization, required provenance, RemoteOK attribution carried structurally, Jooble key never recorded (injection-verified); HttpClient.get_json gains additive headers; Tier B (JSearch) evaluated-not-built; Tier C (Naukri/Foundit/LinkedIn/Indeed/Seek) recorded manual-only -- no permitted programmatic path, no scrapers ever | Accepted |
| [0037](0037-persistence-discover-and-first-profile-writer.md) | SQLite persistence (fidelity-proven drop-in OpportunityRepository incl. close/reopen round-trip; append-only application audit trail), real discover command producing the exact ADR-0026 handoff files with per-source failure isolation, the first MasterProfile writer (yes/no/skip capture -- unrecognized input can never become an answer, injection-verified; unmodeled sections byte-identical), and the founding-brief Excel tracker export | Accepted |
| [0038](0038-decide-layer.md) | Decide layer: deterministic weighted ranking inside the Planner boundary (profile match via Phase 10's unforked keyword machinery 50%, source reliability 20%, freshness 20%, salary-transparency bonus 10%); config filters are hard excludes with named reasons (injection-verified against penalty-conversion), excluded opportunities returned visibly; zero LLM calls in v1; salary floor deliberately absent (no structured field -- named, not silent) | Accepted |
| [0039](0039-learn-pillar.md) | Learn pillar: typed outcome recording attached only to real recorded applications (append-only history), per-variant funnels keyed to prompt/profile/ATS band reading the FULL outcome history with rejection stages separated; raw counts only at personal N -- no significance testing, no bandit routing, mandatory small-sample caveat (injection-verified) and tested absence of prescriptive verdicts | Accepted |
