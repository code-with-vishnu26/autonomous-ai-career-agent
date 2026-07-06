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

## Checking a results artifact against the real gate, without a live call

`career-agent verify-promptfoo --provider {anthropic,groq} [--results-dir DIR]`
calls the exact, unmodified `verify_promptfoo_results` that `apply` calls
before constructing a real verifier -- zero-cost, offline, no API key
needed just to check a file that already exists on disk:

```bash
career-agent verify-promptfoo --provider groq
# reads promptfoo/results/<TRUTHFULNESS_GATE_PROMPT_VERSION>--groq.json
# by default; pass --results-dir to point elsewhere.
```

A `PASS` here means `apply` would pass this same gate for that provider
right now, with whatever is currently on disk.

If it fails on the prompt-content drift check specifically (`"the prompt
text promptfoo recorded running against does not match the current
promptfoo/prompt.txt"`), run the diagnostic below before assuming your
prompt actually changed -- two real, non-drift representation
differences have already been found and fixed (see
`promptfoo_gate.py`'s module docstring for the full history: promptfoo's
own `.txt`-file loader neutralizes CRLF and strips leading/trailing
whitespace, including the file's own trailing newline, before recording
`raw` -- a fresh, unmodified prompt can still legitimately differ from
the on-disk file by exactly that trim):

```bash
career-agent diagnose-promptfoo-drift --provider groq
# reads the same results file verify-promptfoo does; prints lengths,
# SHA-256 hashes (raw and canonicalized), BOM/trailing-newline/CRLF
# presence on each side, and the first differing character with a small
# context window -- never the full prompt or evidence/claim text, so
# it's safe to paste into a bug report.
```

## Artifact policy: local evidence, never committed

`promptfoo/results/*.json` is gitignored. These files are proof that *one
person, on one machine, at one point in time* ran the live suite -- not a
repository-wide fact, and not something a fresh clone should inherit from
history. A fresh install (or CI) has no shortcut: it must run its own live
suite per provider (see "Running it" above) to obtain its own trusted
evidence. Committing a results file would not make it more true, and would
actively mislead: see the security note below for exactly why "checked
into version control" is not the same property as "verified."

## Security note: this checks structure and content, not authenticity

**`verify_promptfoo_results` trusts the JSON in the results file at face
value.** It never re-contacts promptfoo, Groq, or Anthropic -- it has no
way to confirm the file's counters (`successes`/`failures`/`errors`), its
recorded `config.providers` entry, or (as of the prompt-content drift
check documented in `promptfoo_gate.py`'s module docstring) its recorded
`results.prompts[0].raw` text actually came from a real API call, as
opposed to being hand-written or hand-edited to match. A file with
`successes: 10, failures: 0, errors: 0`, the right provider id, and the
current `prompt.txt` text copied in verbatim would pass every check in
this module today, real run or not.

This is an accepted, explicitly-scoped gap, not an oversight:

- **Integrity against accidental drift** (a stale prompt, a partial run, a
  provider mismatch, a since-edited `prompt.txt`) -- this module checks
  for real, fail-closed, and is what its filename convention plus
  ADR-0044's stats/provider/prompt-content checks exist to do.
- **Authenticity against deliberate fabrication** (cryptographic proof a
  real model call actually happened) -- this module does **not** provide
  this, and nothing in this project currently does. A plain content hash
  would not close this gap either: hashing `prompt.txt`, `tests.yaml`, or
  the provider config only proves *which* prompt/tests/provider a results
  file claims to be about, exactly like the checks that already exist --
  it does not, and cannot, prove the file's stats came from a real
  judged run rather than a matching hash typed by hand.

Proportionate, zero-cost options if this gap is ever worth closing
further (not implemented -- named here so the tradeoff is a documented,
deliberate decision rather than a silent gap): recording the real
promptfoo eval's own run id/timestamp and requiring it be "recent"; a
locally-generated manifest (checksums of prompt/tests/config) written by
a wrapper script at eval time, checked at verify time, closing the
"human retypes matching values by hand" case but not a scripted forgery
that also computes correct hashes; a real signed attestation, which would
need a trusted signer and key management this single-user, self-hosted
project has no infrastructure for today. None of these change what is
true right now: **a hand-crafted or hand-edited JSON with correct-looking
values currently satisfies `verify_promptfoo_results`.** Treat a "PASS"
from a results file you did not personally see promptfoo produce with the
same skepticism the truthfulness gate itself applies to an unverified
claim.

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
- `promptfoo/tests/offline_transform_regression/` — three offline,
  no-API-key regressions: (1) `defaultTest.options.transform` is at the
  correct YAML level for the installed promptfoo version -- run this if a
  future promptfoo upgrade makes live validation fail again with
  correct-looking JSON visible in the transcript but every case still
  failing; (2) the real `prompt.txt` renders through Nunjucks without a
  template error -- run this after *any* edit to `prompt.txt`; (3) case
  #7's compound-claim category assertion accepts either valid category
  (see its own README).

## Updating after a prompt change

1. Edit `src/career_agent/llm/prompts.py` — bump
   `TRUTHFULNESS_GATE_PROMPT_VERSION` (never edit a shipped version's text in
   place).
2. Copy the new prompt text into `promptfoo/prompt.txt` — **with single
   braces for any literal JSON example, not the doubled braces
   `prompts.py`'s Python string needs for `.format()`.** Only
   `{{evidence}}`/`{{statement}}` should ever be doubled in `prompt.txt`;
   promptfoo renders it with Nunjucks directly, which reads any other
   `{{`/`}}` as its own (broken) variable syntax -- exactly the bug a live
   `truthfulness-gate-v2` run found and
   `tests/offline_transform_regression/config_prompt_render.yaml` now
   catches offline.
3. Run `npx promptfoo@latest eval --config tests/offline_transform_regression/config_prompt_render.yaml --no-cache`
   (from `promptfoo/`) to confirm the file still renders before spending a
   live API call finding out otherwise.
4. Re-run **both** provider suites above before merging. A prompt change that
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

## Result-gate hardening (ADR-0044)

`verify_promptfoo_results` also requires (not just `successes >= 1` and
`failures == 0`, as before): `errors == 0` (a provider timeout/network
failure is a distinct promptfoo outcome from a judged rejection, and was
previously invisible to this check entirely), `successes` equal to the
*exact* current case count in `tests.yaml` (a partial run must not pass
merely because nothing it did run failed), and the results file's own
recorded `config.providers` entry matching the expected provider id for
`provider_id` (catches a misplaced/renamed results file the filename
convention alone can't).

## A note on Groq free-tier concurrency and queue timeouts

A live run may show `Request ... timed out after 300000ms in queue` on one
or more cases without any judgment being made at all — this is a
provider-side queueing/rate-limit symptom (Groq's free tier for
`openai/gpt-oss-120b` is rate-limited on both requests/minute and
tokens/minute; 4 concurrent long-reasoning calls can exceed that), not a
truthfulness judgment, and promptfoo now counts it as an `error`, not a
`failure` — either way it fails `verify_promptfoo_results`. If you see this,
retry with lower concurrency before assuming anything about the model or
the prompt:

```bash
npx promptfoo@latest eval --config promptfoo/promptfooconfig.groq.yaml \
  --no-cache --max-concurrency 1 \
  -o promptfoo/results/truthfulness-gate-v2--groq.json
```
