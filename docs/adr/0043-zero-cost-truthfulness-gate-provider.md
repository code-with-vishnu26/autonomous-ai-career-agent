# ADR-0043: The truthfulness gate's verifier also gets a free-tier provider, on explicit user override of ADR-0016's exemption

- **Status:** Accepted
- **Date:** 2026-07-05
- **References:** [ADR-0016](0016-truthfulness-gate-verification.md) (the
  cost-cascade exemption this ADR overrides, in part),
  [ADR-0042](0042-groq-free-tier-provider-for-non-exempt-llm-ports.md) (the
  prior decision this ADR partially supersedes)

## Context

ADR-0042 gave `ContentDrafter` and `SemanticKeywordMatcher` a free-tier Groq
branch and deliberately left `ClaimVerifier` untouched — its own text states
"`ClaimVerifier` gains no Groq implementation and no selection logic" and
that `providers.py` is "written so a future edit cannot casually add a
free-tier branch to it." That was the correct call *given the goal at the
time* (reduce cost where ADR-0022/ADR-0034 already established it was safe
to do so, without touching the one port those ADRs never cleared).

The user then gave a direct, explicit instruction: run the entire
application at zero ongoing cost, with no paid-tier exceptions. That
instruction includes `ClaimVerifier`. This ADR records that override
happening, on the record, rather than silently editing ADR-0042's history
to look as if this was the plan all along — it was not; ADR-0042 argued
the opposite, for good reasons that still apply to the *risk*, just not to
whether the user is allowed to accept that risk knowingly.

**The risk has not changed and this ADR does not pretend otherwise.** A
false-approve from `ClaimVerifier` is a fabricated résumé claim reaching a
real submission, which ADR-0016 correctly called catastrophic and
unrecoverable. Presented with that risk explicitly (a question, not a
silent implementation), the user chose to proceed with a free-tier verifier
anyway. This ADR's job is to make that choice as safe as it can structurally
be made, not to pretend the tradeoff away.

## Decision

1. **`GroqClaimVerifier`** (`llm/groq_claim_verifier.py`) is added as a
   second, real `ClaimVerifier` implementation, calling
   `openai/gpt-oss-120b` via Groq's free tier — the strongest reasoning
   model available there, deliberately not the same `llama-3.3-70b-versatile`
   default used for the lower-stakes drafting/matching ports. Same
   fail-closed contract as `AnthropicClaimVerifier`: raises on any failure
   (network error, malformed JSON) rather than ever returning a fabricated
   verdict.
2. **`llm/providers.py`'s `select_claim_verifier`** now prefers Groq when
   `GROQ_API_KEY` is set, falling back to Anthropic — the same pattern as
   the other two ports, reversing ADR-0042's explicit refusal to give this
   port a selection function at all.
3. **The promptfoo gate becomes provider-aware, not just prompt-version-aware.**
   This is the actual compensating control, and it is structural, not a
   policy note: `verify_promptfoo_results` now takes a required
   `provider_id` keyword argument and keys its results filename to
   `{prompt_version}--{provider_id}.json`. Before this change, a single
   prompt-version-keyed filename meant a live-validated pass recorded for
   Anthropic would have silently satisfied the gate for an entirely
   unvalidated Groq verifier the moment one existed — the exact
   "unverified signal trusted as verified" failure mode this project
   refuses everywhere else, just one dimension over from where ADR-0026
   originally closed it. `cli.py` now calls
   `verify_promptfoo_results(claim_verifier.prompt_version, results_dir, provider_id=claim_verifier.provider_id)`
   using whichever verifier `select_claim_verifier` actually returned, so
   the gate checked is always the gate for the class about to be used.
4. **`GroqClaimVerifier` must not be wired into a real `apply` run until the
   promptfoo suite has passed on live calls against it specifically** —
   `promptfoo/promptfooconfig.groq.yaml` is the config for that run,
   written but (like the Anthropic config before it) not runnable in this
   sandbox. This is the validation requirement this ADR does not close: it
   is real, outstanding work for the user to do on their own machine before
   trusting `GroqClaimVerifier` on a real submission, exactly as ADR-0016
   already required for the Anthropic verifier and nothing here waives
   that for either provider.
5. **The import-linter contract** that kept `AnthropicClaimVerifier` out of
   `agents`/`core`/`plugins`/`storage` (ADR-0018) now also forbids importing
   `groq_claim_verifier` from those layers — the same structural reasoning
   applies to both concrete classes equally.

## Consequences

- With `GROQ_API_KEY` set, the entire LLM surface of this project —
  drafting, semantic matching, and the truthfulness gate — runs at zero
  ongoing cost. `ANTHROPIC_API_KEY` becomes fully optional.
- **This is a genuine safety-relevant tradeoff, made explicitly, not
  silently.** The user was asked directly whether the truthfulness gate
  should move to a free model, given the stated risk, before this ADR was
  written or any code changed.
- The compensating control is real but partial: it guarantees a Groq pass
  can never be *confused* with an Anthropic pass, and that neither can be
  used before it is actually validated. It does not, and cannot, guarantee
  `openai/gpt-oss-120b` judges the 12-case adversarial matrix as well as
  Claude Opus did — that is exactly what the (not-yet-run) promptfoo suite
  is for.
- `promptfoo/promptfooconfig.yaml` was renamed to
  `promptfoo/promptfooconfig.anthropic.yaml` for symmetry with the new
  `promptfoo/promptfooconfig.groq.yaml`; `promptfoo/README.md` documents
  running both.
- ADR-0042's specific claim that `ClaimVerifier` "gains no Groq
  implementation and no selection logic" is superseded by this ADR. The
  rest of ADR-0042 (Groq for `ContentDrafter`/`SemanticKeywordMatcher`, the
  provider comparison, the no-runtime-fallback design) stands unchanged.

## Alternatives considered

- **Silently swapping `_MODEL` on `AnthropicClaimVerifier` to a cheaper
  Anthropic tier instead of adding a new provider.** Rejected: still paid,
  doesn't satisfy "zero cost," and blurs the already-recorded
  Haiku/Sonnet/Opus exemption into a single mutable constant instead of a
  distinct, separately-gated class.
- **Making the free-tier swap implicit / not asking the user first.**
  Rejected outright — a false-approve here is the single highest-stakes
  failure mode in the whole system; the standing project discipline is to
  never silently weaken a hard invariant like this one, and the user's own
  originating brief for this change said exactly that ("do not weaken the
  verifier merely to save money... if no option is clearly safe enough, do
  not weaken the verifier"). Surfacing the tradeoff and getting an explicit
  answer is what "not weakening it silently" means in practice.
- **Reusing one promptfoo results filename for both providers with a
  comment warning not to.** Rejected: this project's own standing rule is
  to check the evidence structurally, not trust a comment or a policy — the
  provider-keyed filename is that check, not a suggestion.

## Future revisit criteria

- Live promptfoo results for `openai/gpt-oss-120b` come back materially
  worse than Anthropic's recorded 12-case pass rate — at that point the
  user may want `ANTHROPIC_API_KEY` as an explicit high-confidence opt-in
  for this port specifically, while keeping Groq for the other two.
- Groq deprecates or changes access to `openai/gpt-oss-120b`.
- A future prompt-version bump requires re-running promptfoo for **both**
  providers, not just one — `promptfoo/README.md`'s "Updating after a
  prompt change" section says so explicitly now.
