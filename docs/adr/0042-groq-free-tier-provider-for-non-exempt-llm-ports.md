# ADR-0042: Groq (free tier) as the default provider for the two LLM ports never exempted from cost routing

- **Status:** Accepted
- **Date:** 2026-07-05
- **References:** [ADR-0016](0016-truthfulness-gate-verification.md) (the
  `ClaimVerifier` cost-cascade exemption this decision explicitly does not
  touch), [ADR-0022](0022-resume-generator.md) (`ContentDrafter`'s
  non-exemption), [ADR-0034](0034-ats-score-gate.md)
  (`SemanticKeywordMatcher`'s non-exemption)

## Context

This is a single-user, self-hosted project with no revenue offsetting LLM
spend. Every real call currently goes to Anthropic, at Anthropic's prices,
including two ports that ADR-0022 and ADR-0034 already analyzed and
concluded were safe to route to a cheaper model, and never did: `llm/`'s
own docstring calls the promised Haiku→Sonnet→Opus cascade "still future
work." Cost reduction was left on the table that the architecture already
argued for.

`ClaimVerifier` (ADR-0016) is different in kind, not degree: a
false-approve there is a fabricated claim reaching a real submission,
unrecoverable, which is exactly why it is pinned to the most capable tier
and gated by a passing promptfoo suite before it is ever wired in. Nothing
in this ADR revisits that. This decision is scoped to the two ports whose
own ADRs already established the opposite risk profile.

### Why Groq, not Gemini or OpenRouter

All three have workable free tiers and OpenAI-compatible-ish HTTP surfaces.
The deciding factor was data handling, not price or rate limits, because
every call this project makes carries the user's own resume content and
profile data:

- **Google AI Studio's free tier** explicitly permits Google to use
  submitted content to improve its products, with human review possible,
  unless billing is enabled (which forfeits the free tier's cost benefit
  entirely). Unacceptable for a port that receives the user's résumé text
  and profile JSON on every call.
- **OpenRouter's free tier** proxies to a rotating set of underlying model
  providers per request; the data-handling terms of the specific
  downstream provider serving a given call are not fixed or fully
  disclosed in advance.
- **Groq's services agreement** states Groq is not permitted to use
  inputs or outputs for training or fine-tuning, with no free/paid
  carve-out in that restriction, and inference requests are not retained
  by default. This is the only option among the three where the privacy
  posture doesn't depend on which tier or which day's model rotation the
  user happens to be on.

Rate limits (14,400 requests/day, 30 RPM on Groq's free tier) comfortably
cover a single-user workload. Groq exposes an OpenAI-compatible
`/chat/completions` endpoint, so no new SDK dependency was needed — the
project's existing `httpx` dependency is sufficient.

Free-tier terms from any provider are not a permanent guarantee. This
decision is revisited if Groq's terms change (see Future revisit criteria).

## Decision

1. **`ContentDrafter` and `SemanticKeywordMatcher` gain a second, real
   implementation each** (`GroqContentDrafter`, `GroqSemanticKeywordMatcher`
   in `llm/`), calling Groq's `/chat/completions` endpoint via `httpx`,
   reusing the exact same prompt text and `prompt_version` constants as
   the Anthropic-backed originals. No new prompt, no prompt-version bump —
   the port's contract and prompt did not change, only which model answers
   it.
2. **`ClaimVerifier` gains no Groq implementation and no selection logic.**
   `llm/providers.py`'s `build_claim_verifier` constructs
   `AnthropicClaimVerifier` unconditionally and is the one place in the
   codebase deliberately written so a future edit cannot casually add a
   free-tier branch to it without visibly contradicting its own docstring.
3. **Provider is chosen once, at composition time, never per-call.**
   `llm/providers.py`'s `select_content_drafter`/`select_semantic_matcher`
   prefer Groq when `GROQ_API_KEY` is set, fall back to Anthropic when only
   `ANTHROPIC_API_KEY` is set, exactly as before this ADR if `GROQ_API_KEY`
   is left unset. There is no runtime provider-to-provider fallback: a
   Groq failure raises (drafter) or fails to `[]` (semantic matcher, per
   its existing advisory contract) — it never silently reroutes to the
   paid Anthropic call mid-run. This is what makes "no silent paid
   fallback" true by construction rather than by a check that could rot.
4. **Promptfoo is unaffected.** The promptfoo suite (ADR-0016) validates
   `TRUTHFULNESS_GATE_PROMPT`/`AnthropicClaimVerifier` only. Neither
   `ContentDrafter` nor `SemanticKeywordMatcher` was ever in that suite's
   scope, so this change requires no promptfoo re-run and creates no new
   prompt-version baseline.

## Consequences

- Setting `GROQ_API_KEY` (no card required) removes essentially all
  per-application LLM cost for tailoring drafts and semantic keyword
  matching, while `ANTHROPIC_API_KEY` remains mandatory for `apply` and
  `auto` regardless, because the truthfulness gate is not optional and is
  never routed to Groq.
- A user who sets only `ANTHROPIC_API_KEY` sees no behavior change at all
  — this is an opt-in cost reduction, not a forced migration.
- Draft *quality* (not safety) may shift with the drafting model; the
  truthfulness gate and the ATS ranker gate is what safety actually rests
  on, and both are unchanged.
- The `docs/adr/README.md` index and `ARCHITECTURE.md`'s LLM section need
  a pointer to this ADR (See "Documentation" below).

## Alternatives considered

- **Building the full Haiku→Sonnet→Opus cascade first, then adding Groq as
  a rung.** Rejected as premature scope: the cascade doesn't exist yet,
  and building it is unrelated, larger work this task was not asked to do.
- **Gemini as primary, Groq as fallback.** Rejected on the data-handling
  ground above — Gemini's free tier is unsuitable as a *primary* for a
  port that receives personal resume content on every call regardless of
  fallback ordering.
- **Making `ClaimVerifier` provider-selectable "for symmetry."** Rejected
  outright — the entire point of ADR-0016's exemption is that this port
  is not like the other two; giving it the same selection function would
  create exactly the "someone flips one flag and downgrades the gate"
  failure mode ADR-0016 was written to prevent.

## Future revisit criteria

- Groq's terms of service or free-tier limits change materially.
- The general `llm/` cost-cascade client described in `llm/__init__.py`'s
  docstring is actually built, at which point this ADR's provider
  selection may be superseded by that client's own routing.
- A second free/cheap provider is added for either port, at which point
  `llm/providers.py`'s two-provider `if`/`elif` should become an ordered
  list rather than growing a third branch by hand.
