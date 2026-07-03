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
