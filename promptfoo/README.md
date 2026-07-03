# Truthfulness gate: promptfoo suite

This is the **hard merge gate for the real, Claude-backed `ClaimVerifier`**
(`src/career_agent/llm/claim_verifier.py`), not a nice-to-have (ADR-0016).

`tests/agents/test_truthfulness_gate.py` proves the gate's *orchestration* is
correct (evidence assembly, category mapping, fail-closed aggregation) against
`FakeClaimVerifier`'s deterministic, canned verdicts. It proves **nothing**
about whether a real model actually judges these 12 claims correctly. This
suite is what proves that — against **live Claude calls**, using the exact
same 12-case adversarial matrix the pytest suite is organized around.

**`AnthropicClaimVerifier` must not be wired into the real `apply` path until
this suite passes on live calls.** Passing pytest with the fake verifier is
necessary but not sufficient. This is no longer enforced by policy alone
(ADR-0026): `career-agent apply` calls
`llm/promptfoo_gate.py::verify_promptfoo_results` before constructing the
real verifier, and it checks an actual results artifact on disk — not a
flag typed from memory. See "Running it" below for the exact output path it
looks for.

## Running it

Requires a real `ANTHROPIC_API_KEY` and outbound network access — neither is
available in the Claude Code Remote sandbox this project was built in (the
egress policy blocks it, same as every other live API in this project). Run
this from your own machine, writing results to the path `career-agent apply`
checks — `promptfoo/results/<prompt version>.json`, keyed by the exact
`TRUTHFULNESS_GATE_PROMPT_VERSION` currently in
`src/career_agent/llm/prompts.py` so a stale pass from an old prompt version
is never silently treated as still valid:

```bash
export ANTHROPIC_API_KEY=sk-...
npx promptfoo@latest eval --config promptfoo/promptfooconfig.yaml \
  -o promptfoo/results/<prompt-version>.json
npx promptfoo@latest view   # inspect results in a browser
```

`verify_promptfoo_results` reads that file's `results.stats.successes`/
`failures` and refuses to proceed unless it records at least one success and
zero failures — an empty/no-op run does not count as a pass.

## Files

- `promptfoo/promptfooconfig.yaml` — the eval config: which prompt, which
  provider/model, which test cases.
- `promptfoo/prompt.txt` — **must stay byte-identical** to
  `TRUTHFULNESS_GATE_PROMPT` in `src/career_agent/llm/prompts.py`
  (`TRUTHFULNESS_GATE_PROMPT_VERSION`). There is no automated sync between
  them yet; if you change one, change the other and bump the version.
- `promptfoo/tests.yaml` — the 12-case adversarial matrix, each case asserting
  the expected `verified`/`category` in the model's JSON response.

## Updating after a prompt change

1. Edit `src/career_agent/llm/prompts.py` — bump
   `TRUTHFULNESS_GATE_PROMPT_VERSION` (never edit a shipped version's text in
   place).
2. Copy the new prompt text into `promptfoo/prompt.txt`.
3. Re-run the suite above before merging. A prompt change that breaks any of
   the 12 cases is not mergeable, same as a code change that breaks a test.
