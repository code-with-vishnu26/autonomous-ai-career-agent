"""Positive verification that promptfoo has actually passed.

ADR-0016, ADR-0026, ADR-0043, ADR-0044. ADR-0016 requires the promptfoo
suite to pass on live calls before ``AnthropicClaimVerifier`` is wired into
any real apply path. That requirement was, until now, enforced only by
written policy plus the import-linter contract keeping the concrete class
out of ``agents``/``core``/``plugins``/``storage`` -- ``cli.py`` is
deliberately the one place allowed to construct it (it is the composition
root), which means nothing structural stopped a real, unvalidated verifier
from being wired in at exactly the point it would first matter.

``verify_promptfoo_results`` closes that gap the same way this project
closes every other one: check the evidence, not the claimed verdict. A CLI
flag someone types from memory ("I promise I ran it") is exactly the kind
of unverified assertion the truthfulness gate itself refuses to accept from
a claimed confidence score -- so this checks an actual results artifact on
disk instead, tied to the exact prompt version *and provider* it validated
by filename, and verifies its recorded pass/fail counts, not merely that
the file exists.

ADR-0043 added the provider dimension: once a second real ``ClaimVerifier``
(``GroqClaimVerifier``) existed, a prompt-version-only filename would let a
promptfoo pass recorded for Anthropic silently authorize an entirely
unvalidated Groq verifier, and vice versa -- the exact "unverified signal
trusted as verified" failure mode this file exists to prevent, just moved
one dimension over. ``provider_id`` is now a required keyword argument, not
an optional refinement.

ADR-0044 hardened the check itself, after a live run
(``successes=7, failures=2, errors=1`` against the 10-case matrix) exposed
that the original check -- ``successes >= 1 and failures == 0`` -- never
looked at ``results.stats.errors`` at all. Errors are a distinct promptfoo
outcome from failures (a provider timeout, not a judged-and-rejected
claim); a run with zero failures but a nonzero error count was previously
indistinguishable from a real, complete pass. Now required, all
independently, fail-closed on any missing/malformed field:

- ``errors == 0``
- ``successes == _EXPECTED_CASE_COUNT`` (not merely ``>= 1`` -- a partial
  run that silently evaluated fewer cases than the current matrix must not
  pass just because none of the cases it *did* run failed)
- the results file's own recorded provider id matches the expected id for
  ``provider_id`` (catches a renamed/misplaced results file the filename
  convention alone cannot)

**What this module proves, and what it does not.** Every check above is
*integrity against accidental drift*: a stale prompt, a partial run, a
provider mismatch, a malformed file. None of it is *authenticity against
deliberate fabrication*. ``verify_promptfoo_results`` trusts the JSON
counters and metadata in the results file at face value -- it never
contacts promptfoo, Groq, or Anthropic itself, and has no way to. A
hand-edited or hand-written file with ``successes`` equal to
``_EXPECTED_CASE_COUNT``, ``failures``/``errors`` at ``0``, and a
``config.providers`` entry copied from a real config would satisfy every
check in this module, including the prompt-content check added below,
which a fabricator could defeat just as easily by also copying the real
``prompt.txt`` text into the fake file. Nothing here is a cryptographic
signature or a call-log audit trail; closing that gap for real (e.g. a
signed attestation from the eval run itself) is unimplemented and would be
new scope, not a fix to what exists.

The prompt-content check added after ADR-0044's stats hardening closes one
further *drift* gap, not the authenticity one: ``verify_promptfoo_results``
previously trusted the filename's ``prompt_version`` segment to mean the
results were actually validated against the *current* ``promptfoo/prompt.txt``
text, with nothing checking that promptfoo's own recorded prompt actually
matches -- a version bump without regenerating results, or a hand-edited
``prompt.txt`` after a real run, would go undetected. When a
``prompt.txt`` file exists next to ``results_dir`` (the real, production
layout -- ``results_dir`` is always ``promptfoo/results``, so
``results_dir.parent`` is always ``promptfoo/``), this now compares that
file's exact current text against ``results.prompts[0].raw``, the exact
unrendered prompt text promptfoo itself recorded at evaluation time, and
fails closed on a mismatch. It is skipped -- not failed -- when no sibling
``prompt.txt`` exists (the existing unit tests in this project use bare
``tmp_path`` fixtures with no such file) or when the results payload lacks
a ``results.prompts[0].raw`` string (an older/different promptfoo schema
shape); this is a deliberate best-effort addition layered on top of the
mandatory stats/provider checks above, not a new required field.
"""

from __future__ import annotations

import json
from pathlib import Path

#: Must match the number of cases in promptfoo/tests.yaml. No automated
#: sync exists yet (same accepted limitation as prompt.txt/prompts.py,
#: ADR-0016) -- update this alongside any change to that file's case count.
_EXPECTED_CASE_COUNT = 10

#: The exact provider id string each provider's promptfooconfig.*.yaml
#: declares -- cross-checked against the results file's own recorded
#: config, not just the filename, so a misnamed/misplaced results file
#: cannot be mistaken for the provider it claims to be.
_EXPECTED_PROVIDER_IDS = {
    "anthropic": "anthropic:messages:claude-opus-4-8",
    "groq": "openai:chat:openai/gpt-oss-120b",
}


class PromptfooNotValidatedError(Exception):
    """No passing promptfoo results artifact was found for this prompt/provider.

    Raised instead of trusting an assertion -- the same "check the
    evidence, not the claimed verdict" discipline the truthfulness gate
    itself is built on, now applied to whether the gate's own real
    implementation has actually been validated.
    """


def _recorded_provider_ids(payload: dict[str, object]) -> set[str]:
    """Every provider id promptfoo recorded actually running this eval.

    ``config.providers`` entries are either bare id strings or
    ``{"id": ..., "config": {...}}`` objects, depending on how the YAML
    was written -- both shapes are normalized here.
    """
    providers = payload["config"]["providers"]  # type: ignore[index]
    ids: set[str] = set()
    for entry in providers:
        if isinstance(entry, str):
            ids.add(entry)
        elif isinstance(entry, dict) and "id" in entry:
            ids.add(str(entry["id"]))
    return ids


def _recorded_prompt_raw(payload: dict[str, object]) -> str | None:
    """The exact unrendered prompt text promptfoo recorded at eval time.

    Returns ``None`` (never raises) on any shape that doesn't match --
    callers treat that as "nothing to compare against", not an error, since
    this check is best-effort by design (see module docstring).
    """
    try:
        results = payload["results"]  # type: ignore[index]
        prompts = results["prompts"]  # type: ignore[index]
        raw = prompts[0]["raw"]
        return raw if isinstance(raw, str) else None
    except (KeyError, IndexError, TypeError):
        return None


def verify_promptfoo_results(
    prompt_version: str, results_dir: Path, *, provider_id: str
) -> None:
    """Raise unless a matching results file proves a complete, clean pass.

    The filename convention (``{prompt_version}--{provider_id}.json``) ties
    a results artifact to the exact prompt
    version *and* provider it validated -- a stale pass from a
    since-changed prompt, or a pass recorded for a different
    ``ClaimVerifier`` implementation, has a different filename and will not
    be found here. Beyond that, this checks (ADR-0044): zero failures, zero
    errors, every one of the current matrix's cases actually evaluated
    (not merely at least one success), and the file's own recorded provider
    id matching what ``provider_id`` expects -- not merely that the file
    exists, or that some subset of cases happened to pass.

    Best-effort, additional to the above: if ``results_dir.parent /
    "prompt.txt"`` exists (the real production layout), the results file's
    own recorded ``results.prompts[0].raw`` must match that file's current
    text exactly -- a drift check, not an authenticity one (see module
    docstring). Skipped silently when no such sibling file exists or the
    results payload doesn't carry that field.
    """
    results_path = results_dir / f"{prompt_version}--{provider_id}.json"
    if not results_path.exists():
        raise PromptfooNotValidatedError(
            f"No promptfoo results found for prompt version {prompt_version!r} "
            f"/ provider {provider_id!r} at {results_path}. Run the promptfoo "
            f"suite for this provider on your own machine (real network + its "
            f"API key required -- see promptfoo/README.md) and write its "
            f"output there:\n"
            f"  npx promptfoo@latest eval --config "
            f"promptfoo/promptfooconfig.{provider_id}.yaml -o {results_path}"
        )
    try:
        payload = json.loads(results_path.read_text())
        stats = payload["results"]["stats"]
        failures = int(stats["failures"])
        successes = int(stats["successes"])
        errors = int(stats["errors"])
        recorded_provider_ids = _recorded_provider_ids(payload)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise PromptfooNotValidatedError(
            f"{results_path} exists but could not be read as a valid "
            f"promptfoo results file: {exc}"
        ) from exc

    problems: list[str] = []
    if failures != 0:
        problems.append(f"{failures} failing case(s)")
    if errors != 0:
        problems.append(
            f"{errors} error(s) (provider/network failure, not a judged rejection)"
        )
    if successes != _EXPECTED_CASE_COUNT:
        problems.append(
            f"{successes} success(es), expected exactly {_EXPECTED_CASE_COUNT} "
            f"(the full current matrix -- a partial run does not count)"
        )
    expected_provider = _EXPECTED_PROVIDER_IDS.get(provider_id)
    if expected_provider is not None and expected_provider not in recorded_provider_ids:
        problems.append(
            f"recorded provider(s) {sorted(recorded_provider_ids)!r} do not "
            f"include the expected {expected_provider!r} for provider_id "
            f"{provider_id!r}"
        )
    prompt_txt_path = results_dir.parent / "prompt.txt"
    if prompt_txt_path.exists():
        recorded_raw = _recorded_prompt_raw(payload)
        if recorded_raw is not None and recorded_raw != prompt_txt_path.read_text():
            problems.append(
                f"the prompt text promptfoo recorded running against does not "
                f"match the current {prompt_txt_path} -- this results file was "
                f"validated against a different prompt (drift check only; see "
                f"module docstring for what this does and does not prove)"
            )

    if problems:
        raise PromptfooNotValidatedError(
            f"{results_path} does not prove a complete, clean pass for "
            f"prompt version {prompt_version!r} / provider {provider_id!r}: "
            + "; ".join(problems)
            + "."
        )
