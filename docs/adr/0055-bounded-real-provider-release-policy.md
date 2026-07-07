# ADR-0055: Bounded real-provider release policy, cost bounding, and evidence-invalidation triggers (Phase 29)

- **Status:** Accepted
- **Date:** 2026-07-07
- **References:** ADR-0016/0044 (truthfulness gate + Layer-1 precheck),
  ADR-0043 (Groq free-tier verifier, provider/version-keyed Promptfoo),
  ADR-0022 (drafter is recoverable-if-wrong), ADR-0034 (ATS gate + bounded
  retailor loop), ADR-0053 (revision authority), ADR-0054 (prepare-only
  release gate)

## Context

Phase 28 established (offline) that the deterministic, prepare-only
architecture is coherent and safe. Phase 29's question is different:
**does the real provider-backed path produce useful output while every
deterministic safety boundary still holds, under a tightly bounded,
explicitly-opted-in live run — and what would make prior live evidence
stale?**

A fresh audit (main `9765165`, baseline **657 passed / 0 skipped**, ruff
clean, import-linter 4/4) mapped the real LLM path. **This environment has
no `GROQ_API_KEY`/`ANTHROPIC_API_KEY`, no `.env`, and no machine-local
`promptfoo/results/` artifact**, so a live real-provider run is **not
possible here (BLOCKED_BY_CONFIGURATION)** and was not performed or
simulated — the controlled smoke run is a user-local action, defined below.
**Decision: Option A** — no production code, no smoke-harness subsystem
(`career-agent apply` already *is* the bounded prepare-only real-provider
path, and a harness's live path could not be validated here anyway); this
ADR plus drift-guard tests (`tests/test_phase29_provider_release_gate.py`).

## Real-provider inventory (exact, code-verified)

| Component | Groq (free, **preferred**) | Anthropic (paid, fallback) | Promptfoo-gated | Recoverable if wrong |
|---|---|---|---|---|
| ClaimVerifier (truthfulness) | `openai/gpt-oss-120b` (reasoning; `max_tokens=2000`, `reasoning_effort=low`, `include_reasoning=False`) | `claude-opus-4-8` | **YES** (ADR-0043) | No — highest-stakes |
| ContentDrafter | `llama-3.3-70b-versatile` | `claude-opus-4-8` | No | Yes — gate catches downstream (ADR-0022) |
| SemanticKeywordMatcher | `llama-3.3-70b-versatile` | `claude-haiku-4-5-20251001` | No | Yes — advisory only (ADR-0034) |

Selection (`llm/providers.py`): Groq-if-key → Anthropic-if-key → raise
(verifier/drafter) / `None` (matcher). With **both** keys → Groq. Model
identifiers are hardcoded constants, pinned by the new drift-guard tests.
Groq HTTP timeout is 30 s. Empty-string key → falls through (fail-closed);
whitespace-only key → currently selects and then fails at the call (a
documented low-severity, fail-closed limitation, pinned by test).

## Cost / call bounding (the live budget)

One prepare-only run's LLM calls are **structurally bounded** (no unbounded
agent loop):

- **Best case** (draft passes ATS on the first try): `1` drafter call
  + `V` verifier calls, where `V` = the number of *ambiguous* claims (the
  Layer-1 precheck, ADR-0044, resolves deterministically-safe/unsafe claims
  with **zero** model calls) + up to `1` matcher call.
- **Worst bounded case**: the retailor loop runs at most
  `_MAX_ATS_RETRIES = 2` extra iterations, each adding `1` drafter + one
  full re-gate (`≤ V` verifier calls) + `1` matcher call. So total ≤
  `3` drafter + `3·V` verifier + `3` matcher calls — finite and knowable.

Per-call tokens are capped (`max_tokens`; the reasoning verifier at 2000,
covering reasoning + answer). **Monetary cost: UNKNOWN in absolute terms** —
Groq's free tier may absorb it (not the same as zero intrinsic cost), and
Anthropic (`claude-opus-4-8`) is paid; exact pricing is not asserted here
(not browsed). Reasoning tokens count against `max_tokens`, so a reasoning
blow-up cannot silently inflate a call beyond the cap.

## Safety under the real path (what already holds, proven offline)

- **Prompt injection from the JD cannot promote an unsupported claim.** The
  JD reaches the *drafter* (may influence wording) but never the gate
  (`verify(draft, profile)` has no JD parameter); every drafter output is
  re-gated; an unsupported skill fails structural membership; an
  injection-JD end-to-end test already proves a rejected application
  (ADR-0053). A malformed/reasoning-preamble/truncated provider response is
  a parse error → explicit block, never a silent pass
  (`test_groq_providers.py`).
- **The truthfulness release gate is enforced before the live verifier is
  used**: `apply`/`auto` call `verify_promptfoo_results` before constructing
  the verifier; a missing/malformed/wrong-provider/wrong-version/drifted
  artifact blocks (fail-closed).

## What Phase 29 proves vs. what Promptfoo proves (distinct)

- **Promptfoo** proves: the configured verifier prompt+provider+model passes
  the adversarial evaluation suite recorded in that artifact.
- **A Phase-29 controlled smoke run** would prove: the composed
  provider-backed resume path produces one acceptable, safe output under one
  bounded scenario.
- **Neither** proves universal correctness, statistical production
  reliability, all JDs/candidates, or any future model version.

## Evidence-invalidation triggers (Section 24)

Any prior live smoke evidence (and, where noted, the Promptfoo artifact)
becomes **stale** and must be re-established on:

1. truthfulness **prompt version** change → Promptfoo artifact invalid;
2. **verifier provider** change (Groq↔Anthropic) → new provider-keyed
   Promptfoo artifact required;
3. any **model identifier** change (the drift-guard tests fail loudly) →
   re-run live Promptfoo + smoke;
4. a silent **model-alias retarget** by the provider (not detectable from
   the identifier alone — a residual risk, stated);
5. gate-policy / Layer-1-precheck / JSON-parser / retry-policy change.

## Controlled real-provider smoke procedure (user-run, local)

Because a live call needs a real key, a valid local Promptfoo artifact, and
explicit human opt-in — none present in CI — this is a **user-run** release
step, not an automated one:

1. offline preflight: `pytest` / `ruff` / `lint-imports` green;
2. `career-agent verify-promptfoo --provider groq` PASS (do not regenerate
   the artifact to satisfy this);
3. run `career-agent apply` against the **synthetic** Aarav-Rao profile and
   a synthetic JD containing an inert injection sentence — concurrency 1,
   one opportunity, stopping at confirmation (no submission is reachable,
   ADR-0054);
4. build a **claim ledger** over the accepted resume: any surviving
   unsupported skill/metric/seniority/action is a **safety failure**
   (BLOCKED_BY_SAFETY), regardless of quality;
5. apply the human quality review (truthfulness/relevance/specificity/…)
   — quality is judged separately from safety;
6. optionally repeat ≤ 3 samples for variance (descriptive only, no
   statistical claim).

A machine-local, **gitignored** smoke-evidence file (git_sha, provider_id,
model_id, prompt_version, fixture digests, call/token counts, gate verdicts,
ATS score, revision count, output digest, quality scores — **never** keys or
private resume/JD content) is the recommended record; it is not committed
and no code is added here to generate it.

## Release decision

**RELEASE_READY_WITH_LIMITATIONS.** The deterministic safety architecture is
release-ready and proven offline; the **real-output quality** and the
**live-path integration under a real provider** remain validated only by the
user's local controlled smoke run (BLOCKED_BY_CONFIGURATION in this
environment — no keys/artifact). No unsupported claim can survive the gates
by construction, but "the real model produces genuinely useful resumes" is a
per-user, per-provider judgment this phase cannot make on the user's behalf.

## Consequences

- New: `tests/test_phase29_provider_release_gate.py` (model-identifier drift
  guards; bounded token/retry budget; empty/whitespace-key edges; verifier
  Promptfoo-gate scope). No production code, no dependency, no prompt-version
  bump, no Promptfoo/truthfulness/ATS/idempotency/journal/submission-
  reachability change; no live or paid API call.

## Future revisit criteria

Revisit when a live smoke run is actually performed (record its evidence and
verdict here), when a model/provider/prompt change fires an invalidation
trigger, or if cost ever needs a fail-closed in-code budget ceiling (not
justified today — the call graph is already bounded).
