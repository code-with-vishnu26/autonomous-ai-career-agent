# Offline regressions: harness bugs found during live validation

Three independent, offline, no-API-key regressions -- each proving a real
bug (or a genuinely over-constrained assertion) found during
`GroqClaimVerifier`'s live validation, and its fix, without any network
call or real model.

## 1. `options.transform` placement (ADR-0043)

Proves `promptfooconfig.groq.yaml`'s `defaultTest.options.transform` is at
the correct YAML level for the installed `promptfoo` version, and that the
same key placed as a bare sibling of `assert` (the mistake made and then
corrected during validation) silently does nothing.

Uses a local mock provider (`echoProvider.js`) that returns a canned
`"Thinking: ...\n{json}"` response shaped exactly like the real live
`openai/gpt-oss-120b` output recorded during validation -- this is pure
fixture data, not a real model call.

```bash
cd promptfoo/tests/offline_transform_regression
npx promptfoo@latest eval --config config_fixed.yaml --no-cache
# expect: 2 passed, 0 failed

npx promptfoo@latest eval --config config_broken.yaml --no-cache
# expect: 0 passed, 1 failed -- confirms the bare `transform` key is a no-op
```

If `config_fixed.yaml` ever stops passing, or `config_broken.yaml` ever
starts passing, promptfoo's transform-resolution behavior has changed
between versions and `promptfooconfig.groq.yaml` needs re-checking against
whatever the new installed version actually reads -- don't assume the fix
here is permanent across promptfoo upgrades.

## 2. `prompt.txt` must render through Nunjucks without a template error (ADR-0044)

Points at the **real** `promptfoo/prompt.txt` (not a copy) with the same
mock provider. Catches the exact bug found during the `truthfulness-gate-v2`
live validation: the JSON example line (`{"verified": ...}`) needs *single*
braces, since `prompt.txt` is rendered by promptfoo's own Nunjucks engine
directly (not Python's `.format()`, which is why the source constant in
`prompts.py` needs *doubled* braces there -- the two files have opposite
escaping requirements, and copying one's text directly into the other
without converting between them is exactly what caused the bug this
regression catches).

```bash
cd promptfoo/tests/offline_transform_regression
npx promptfoo@latest eval --config config_prompt_render.yaml --no-cache
# expect: 1 passed, 0 failed, 0 errors
# a "Template render error: ... expected variable end" here means prompt.txt
# has a stray double-brace outside of {{evidence}}/{{statement}} again
```

## 3. Compound-claim category flexibility for matrix case #7 (ADR-0044)

A live `truthfulness-gate-v2` Groq run correctly rejected `"Led a team of
8 engineers"` (`verified: false`, high confidence) but chose
`unsupported_action_inference` where the original assertion required
exactly `metric_unsupported`. Both are genuinely correct: the claim has
two independently unsupported dimensions -- the metric ("8", nowhere in
evidence) and the action ("Led", nowhere in evidence) -- and the prompt
states no precedence between them for a claim matching both descriptions.
This project's own deterministic Layer-1 precheck
(`domain/truthfulness_predicates.py`) picks `metric_unsupported` first
only because its rules happen to run in that order -- an implementation
detail, not a semantic ruling. `promptfoo/tests.yaml`'s case #7 now accepts
either category; `verified === false` remains unconditional and was never
relaxed.

Proves offline (canned responses standing in for a model picking either
valid category) that the relaxed assertion accepts both:

```bash
cd promptfoo/tests/offline_transform_regression
npx promptfoo@latest eval --config config_compound_category.yaml --no-cache
# expect: 2 passed, 0 failed, 0 errors
```
