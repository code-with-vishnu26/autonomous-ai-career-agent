# ADR-0044: Formal claim-evidence entailment model + deterministic Layer-1 precheck

- **Status:** Accepted
- **Date:** 2026-07-06
- **References:** [ADR-0016](0016-truthfulness-gate-verification.md) (the
  12-case matrix this ADR revises 4 cases of), [ADR-0034](0034-ats-score-gate.md)
  (the curated-taxonomy, no-NLP-model precedent this ADR follows),
  [ADR-0043](0043-zero-cost-truthfulness-gate-provider.md) (the provider+version
  keying this ADR relies on to invalidate stale results)

## Context

A live promptfoo run against `GroqClaimVerifier` (after fixing three
unrelated harness bugs — token-budget truncation, a reasoning-preamble leak,
and a promptfoo config-key placement mistake, all fixed in prior commits on
this branch) came back 8/10. Reviewing the two failures and the eight
passes side by side surfaced a real policy question, not a bug: four of the
eight passing cases rest on an assumption — "a skill noun proves an action,"
"any honest-sounding rephrase is entailed" — that was never actually
justified against a formal notion of entailment. It was reviewer-drafted,
reasonable-sounding, and wrong to keep unexamined the moment someone asked
"is a skill-list entry actually evidence that the skill was *used* for
something specific?"

The obvious two responses are both wrong. Reverting to "keep the current
standard because ADR-0016 accepted it" treats prior acceptance as proof
rather than a decision that can be revisited with better reasoning — exactly
the deference this project's own standing discipline refuses everywhere
else. Mechanically flipping all four disputed cases to `false` is equally
lazy in the other direction: one of the four (`"Cut pipeline runtime 40%"` →
`"Improved system performance"`) *is* a genuine, checkable safe abstraction,
and calling it unsafe merely because three of its siblings turned out to be
would be exactly the "stricter at any cost" failure mode this ADR was asked
not to produce.

## Decision

### 1. A formal, bounded entailment model — not full predicate logic

Four predicates are checked **deterministically, over a closed vocabulary**,
in a new pure-domain module,
`src/career_agent/domain/truthfulness_predicates.py`:

- **technology** (reusing the ATS gate's own curated taxonomy,
  `skills_taxonomy.py` — no duplicated vocabulary)
- **metric** (any number, tolerant of a trailing `+` on an evidenced number)
- **action verb strength** (a closed, ranked table: `used`/`improved` < `built`/
  `containerized` < `designed`/`engineered` < `architected`/`led`/`owned`)
- **seniority** (a closed list of title words)

Full predicate decomposition (subject/object/scope/causal relation, as a
literal research survey would enumerate) is **not** attempted. This project
already made this exact call once: ADR-0034 rejected a spaCy-based NLP
pipeline for ATS keyword extraction in favor of curated-taxonomy, pure-Python
matching, specifically because a gate whose vocabulary depends on a model
artifact is only deterministic conditional on that artifact's version. The
same reasoning applies here, harder — object/scope/causal decomposition
needs real parsing this project has no zero-cost, deterministic way to do
reliably. Those predicates remain the LLM's job (Layer 4), by explicit
design, not by omission.

### 2. Three-valued output, open-world semantics

`precheck_claim` returns `"safe"`, `"unsafe"`, or `"ambiguous"` — never a
value construed as "probably fine." An early draft of this module made
`"ambiguous"` unreachable: any claim that didn't trip an unsafe rule was
classified `"safe"`, which is exactly the "absence of contradiction is
evidence of support" mistake this project refuses everywhere else. Caught by
this ADR's own test suite (`test_unresolved_claim_defaults_to_ambiguous_not_safe`)
before merge, not after. The fix: `"safe"` requires every remaining content
word in the claim to be *positively explained* — either literally present in
the evidence, or drawn from a small, closed vocabulary of vague,
non-quantified outcome words (`performance`, `efficiency`, `reliability`,
...) that a genuine weakening is allowed to introduce. A claim about an
unrelated, unevidenced topic that merely avoids naming a new technology or
number is `"ambiguous"`, not `"safe"` — it falls through to the LLM, as it
always did before this ADR.

### 3. The four worked disputed cases, decided individually, not mechanically

- **#1 ("Built" → "Architected... high-throughput")**: **flips to BLOCK.**
  "Architected" (verb rank 4) is not evidenced where the profile only shows
  "Built" (rank 2), for the same object. This is the rule that would also
  catch "Led"/"Owned"/"Directed" claimed over evidenced "Used"/"Built"/
  "Developed" — a real, general escalation pattern, not a one-off.
- **#8 ("Cut pipeline runtime 40%" → "Improved system performance")**:
  **stays APPROVE**, on its own merits, via the safe-abstraction rule (§2):
  no new technology, no new number, no verb escalation, and every remaining
  word ("system", "performance") is a recognized vague-outcome word. This is
  the case that proves this ADR did not simply tighten everything — the one
  disputed case that survives scrutiny does so because it is genuinely safe,
  not because it went unexamined.
- **#9 (Docker skill → "Containerized services using Docker")**: **flips to
  BLOCK.** Docker is real, but appears only in the bare skills list — never
  co-occurring with any action/verb in the work or project evidence. A skill
  noun is evidence of familiarity, not of a specific accomplishment.
- **#11 (PostgreSQL skill → "relational database design (PostgreSQL)")**:
  **flips to BLOCK**, same reasoning as #9, applied to a competency noun
  ("design") rather than a verb.
- **#5 (title escalation)** was already BLOCK and stays BLOCK, but its
  category changes from the overloaded `employer_mismatch` to the new,
  precise `unsupported_seniority` — the employer (Techco) was never in
  dispute; only the title was.
- **#10 (Django-based "microservices platform")** was already BLOCK and
  stays BLOCK, but the *mechanism* changes: `"Microservices"` is a named,
  curated-taxonomy technology with zero evidence anywhere (not even a
  skill), caught deterministically at Layer 1 — a stronger, cheaper,
  auditable reason than the previous reliance on the LLM's semantic
  judgment for this specific claim. A companion test
  (`test_case_10b_a_genuinely_evidenced_technology_is_not_blocked`) proves
  this isn't a Django false-positive: `"Used Django"` alone is not blocked.

### 4. A precision limit, found and fixed before merge, documented rather
than hidden

An early version of the skill-only-action rule (Rule 4) also fired on case
#10's claim (`"Built a Django-based microservices platform..."`), for the
wrong reason (Django being skill-only) — masking the actual disputed content
("microservices platform") and breaking that test's specific proof that the
block is *not* a Django false-positive. Fixed by bounding Rule 4 to short
claims (`<= 6` words): this project has no parser to tell whether a
technology token in a longer claim is the direct object of the action word
or an incidental modifier of some other, separately-fabricatable object, so
longer claims are deliberately left to Rule 1 (if the fabricated technology
is itself unevidenced, as #10's is) or Layer 4. Rule 4 is also bounded to
verb rank ≥ 2: `"Used Django"` (rank 1, a near-synonym of "has this skill")
is not flagged, only accomplishment-shaped verbs are.

### 5. Wiring: Layer 1 runs before Layer 4, never replaces it

`agents/resume/gate.py`'s `_check_claim` calls `precheck_claim` first.
`"unsafe"` blocks immediately (no LLM call — a fabrication rule this project
can prove deterministically doesn't need a probabilistic second opinion to
confirm it). `"safe"` approves immediately (same reasoning, in the other
direction — an abstraction this project can prove is safe doesn't need to
spend an LLM call re-deriving that). Only `"ambiguous"` reaches
`self._verifier.verify_claim` — exactly the claims Layer 1 cannot resolve on
a closed vocabulary. This is strictly additive: nothing about the verifier's
own contract, the confidence threshold, or the fail-closed exception
handling changed.

### 6. Prompt version bump: `truthfulness-gate-v1` → `truthfulness-gate-v2`

The prompt text changed (the same four rules Layer 1 encodes are now stated
explicitly, so Layer 4 applies a *consistent* standard on the claims it
still sees) and two new `ClaimVerdict`/`RejectionReason` categories were
added (`unsupported_action_inference`, `unsupported_seniority`). Per
ADR-0016's own rule, a shipped prompt version's text is never edited in
place — this is `v2`, not a `v1` patch. ADR-0043's provider+version-keyed
promptfoo results filenames (`{prompt_version}--{provider}.json`) mean a
`v1` pass **cannot** satisfy a `v2` check by construction: this closes
requirement #12 of the originating brief ("ensure old validation results
cannot authorize the new policy... ensure Groq validation cannot authorize
Anthropic") without any new code — the mechanism ADR-0043 already built
generalizes to a version change for free.

## Consequences

- **Both `ClaimVerifier` implementations are unvalidated against
  `truthfulness-gate-v2`.** The prior 8/10 Groq result was against `v1`
  content and does not carry forward. A fresh live run, on the user's own
  machine, against both `promptfooconfig.anthropic.yaml` and
  `promptfooconfig.groq.yaml`, is required before either verifier may be
  used for a real submission. Neither `career-agent apply` nor
  `career-agent auto` is affected structurally by this gap — `verify_promptfoo_results`
  already refuses to construct an unvalidated verifier; there is nothing new
  to enforce here, only new validation work to do.
- Two claims that would have silently passed before this ADR
  (`"Containerized services using Docker"`, `"relational database design
  (PostgreSQL)"`, when the skill is real but never demonstrated) are now
  blocked. This may surface in real tailoring runs as more `unsupported_action_inference`
  rejections than before — a truthfulness improvement, not a regression, but
  a visible behavior change worth naming.
- `agents/planner/decide.py`'s and other unrelated deterministic scorers are
  untouched. `keyword_sensitivity` (the previous commit on this branch) is
  untouched and unaffected.
- Downstream fixtures that used the now-unsafe "Containerized services with
  Docker" phrasing to exercise the ATS retailor loop
  (`tests/agents/test_ats_gate_loop.py`) were updated to a truthful
  familiarity phrasing ("Skilled in Docker") that preserves the exact same
  ATS keyword-coverage credit — the loop's own real, computed 60/69/78
  score arithmetic is unchanged.

## Alternatives considered

- **Keep the four disputed cases as-is because ADR-0016 already accepted
  them.** Rejected — prior acceptance is not evidence the standard was
  correct, only that it was reasonable at the time with the information
  available then. This project's own truthfulness gate refuses to accept
  "no counter-evidence was raised" as proof of a claim; applying a weaker
  standard to its own governing ADR would be inconsistent.
- **Flip all four disputed cases to BLOCK uniformly.** Rejected — #8 survives
  a genuine, checkable safe-abstraction test; blocking it anyway would be
  false-positive-guard regression for no reason, optimizing for "looks
  strict" over being correct.
- **Build the full 8-layer hybrid verifier architecture sketched in the
  originating research brief** (predicate decomposition, typed entailment,
  Datalog-style rules, an evidence graph, human review). Rejected as
  premature scope: four deterministic predicates already resolve the
  disputed cases and materially reduce the claims reaching the LLM at all;
  building graph/Datalog machinery with no evidence it is needed at this
  project's actual scale would be exactly the "sophistication for its own
  sake" the same brief explicitly warned against.
- **A general, un-bounded skill-only-action rule with no word-count or verb-rank
  floor.** Rejected after it produced an actual, caught precision failure
  (misclassifying matrix case #10 for the wrong reason) — bounded instead,
  with the bound's reasoning recorded in the rule's own comment, not
  silently dropped.

## Future revisit criteria

- A live promptfoo run against `truthfulness-gate-v2` (either provider)
  regresses below what `v1` scored on the cases that carried forward
  unchanged (#2, #3, #4, #6, #7, #12) — would indicate the new prompt
  language confused the model on cases it previously judged correctly.
- Real tailoring runs show `unsupported_action_inference` false-blocking
  claims a human would consider clearly honest — the Rule 4 word-count/verb-rank
  bounds, or the safe-abstraction neutral-outcome-word list, need
  broadening, with new test cases recorded the same way this ADR's own
  disputed-case audit was.
- The object/scope/causal-relation predicates this ADR deliberately left to
  Layer 4 prove to be a recurring source of missed fabrications at real
  scale — would justify the graph/evidence-path research direction named
  and deferred here.
