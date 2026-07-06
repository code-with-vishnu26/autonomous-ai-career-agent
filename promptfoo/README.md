# Truthfulness gate: promptfoo suite

This is the **hard merge gate for the real `ClaimVerifier` implementations**
(`src/career_agent/llm/claim_verifier.py` for Anthropic, `groq_claim_verifier.py`
for Groq), not a nice-to-have (ADR-0016, ADR-0043).

`tests/agents/test_truthfulness_gate.py` proves the gate's *orchestration* is
correct (evidence assembly, category mapping, fail-closed aggregation) against
`FakeClaimVerifier`'s deterministic, canned verdicts. It proves **nothing**
about whether a real model actually judges these 12 claims correctly. This
suite is what proves that — against **live calls to whichever provider you're
validating**, using the exact same 12-case adversarial matrix the pytest suite
is organized around.

**Neither `AnthropicClaimVerifier` nor `GroqClaimVerifier` may be wired into
the real `apply` path until this suite passes on live calls for that specific
provider.** Passing pytest with the fake verifier is necessary but not
sufficient. This is no longer enforced by policy alone (ADR-0026):
`career-agent apply` calls `llm/promptfoo_gate.py::verify_promptfoo_results`
before constructing the real verifier it selected, checking an actual results
artifact on disk keyed to that exact provider — not a flag typed from memory,
and not a pass recorded for the *other* provider. See "Running it" below.

## Running it

Each provider needs its own live run, on your own machine — neither is
available in the Claude Code Remote sandbox this project was built in (the
egress policy blocks it, same as every other live API in this project).
Results are written to `promptfoo/results/<prompt version>--<provider>.json`,
the exact path `career-agent apply` checks for whichever provider it selected
(`GROQ_API_KEY` set → `groq`; otherwise `anthropic`):

```bash
# Anthropic (paid)
export ANTHROPIC_API_KEY=sk-...
npx promptfoo@latest eval --config promptfoo/promptfooconfig.anthropic.yaml \
  -o promptfoo/results/<prompt-version>--anthropic.json

# Groq (free tier)
export GROQ_API_KEY=gsk_...
npx promptfoo@latest eval --config promptfoo/promptfooconfig.groq.yaml \
  -o promptfoo/results/<prompt-version>--groq.json

npx promptfoo@latest view   # inspect results in a browser
```

`verify_promptfoo_results` reads the relevant file's `results.stats.successes`/
`failures` and refuses to proceed unless it records at least one success and
zero failures — an empty/no-op run does not count as a pass. A pass for one
provider is never treated as a pass for the other, by filename construction.

## Files

- `promptfoo/promptfooconfig.anthropic.yaml` — the Anthropic eval config.
- `promptfoo/promptfooconfig.groq.yaml` — the Groq eval config
  (`openai/gpt-oss-120b`, ADR-0043).
- `promptfoo/prompt.txt` — **must stay byte-identical** to
  `TRUTHFULNESS_GATE_PROMPT` in `src/career_agent/llm/prompts.py`
  (`TRUTHFULNESS_GATE_PROMPT_VERSION`), and is shared by both configs. There
  is no automated sync between it and `prompts.py` yet; if you change one,
  change the other and bump the version.
- `promptfoo/tests.yaml` — the 12-case adversarial matrix, each case asserting
  the expected `verified`/`category` in the model's JSON response. Shared by
  both provider configs.
- `promptfoo/tests/offline_transform_regression/` — an offline, no-API-key
  regression proving `promptfooconfig.groq.yaml`'s
  `defaultTest.options.transform` is at the correct YAML level for the
  installed promptfoo version (and that the same key one level up, as a
  bare sibling of `assert`, silently does nothing). Run this first if a
  future promptfoo upgrade makes `GroqClaimVerifier`'s live validation
  start failing again with correct-looking JSON visible in the transcript
  but every case still failing -- see its own README.

## Updating after a prompt change

1. Edit `src/career_agent/llm/prompts.py` — bump
   `TRUTHFULNESS_GATE_PROMPT_VERSION` (never edit a shipped version's text in
   place).
2. Copy the new prompt text into `promptfoo/prompt.txt`.
3. Re-run **both** provider suites above before merging. A prompt change that
   breaks any of the 12 cases, on either provider, is not mergeable, same as
   a code change that breaks a test.

## `truthfulness-gate-v2` (ADR-0044)

The prompt and 4 of the 12 test cases changed on this bump: a skill noun
alone no longer proves an action was performed with it, and a stronger
ownership/action verb ("architected"/"led") is no longer automatically
entailed by a weaker one ("built"/"used") for the same object. Cases #1, #9,
#11 flipped from "must be verified" to "must be blocked"; #5's expected
category changed from `employer_mismatch` to the new, more precise
`unsupported_seniority`. See ADR-0044 for the full audit and reasoning, and
`src/career_agent/domain/truthfulness_predicates.py` for the deterministic
Layer-1 precheck that now applies the same rules structurally, before this
prompt is ever called, for the claims Layer 1 can resolve on its own.

**Any `truthfulness-gate-v1` results file is void.** `verify_promptfoo_results`
keys on the exact prompt version by filename
(`{prompt_version}--{provider}.json`), so a `v1` pass cannot satisfy a `v2`
check by construction — this is not a manual step to remember, it is
structural. A fresh live run against `truthfulness-gate-v2` is required for
both providers before either `ClaimVerifier` may be used for real.
