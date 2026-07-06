# Offline regression: `options.transform` placement (ADR-0043)

Proves, without any network call or API key, that
`promptfooconfig.groq.yaml`'s `defaultTest.options.transform` is at the
correct YAML level for the installed `promptfoo` version, and that the
same key placed as a bare sibling of `assert` (the mistake made and then
corrected during `GroqClaimVerifier`'s live validation) silently does
nothing.

Uses a local mock provider (`echoProvider.js`) that returns a canned
`"Thinking: ...\n{json}"` response shaped exactly like the real live
`openai/gpt-oss-120b` output recorded during validation -- this is pure
fixture data, not a real model call.

## Running it

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
