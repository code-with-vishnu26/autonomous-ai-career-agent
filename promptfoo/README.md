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

## Updating after a prompt change

1. Edit `src/career_agent/llm/prompts.py` — bump
   `TRUTHFULNESS_GATE_PROMPT_VERSION` (never edit a shipped version's text in
   place).
2. Copy the new prompt text into `promptfoo/prompt.txt`.
3. Re-run **both** provider suites above before merging. A prompt change that
   breaks any of the 12 cases, on either provider, is not mergeable, same as
   a code change that breaks a test.
