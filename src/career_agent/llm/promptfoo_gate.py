r"""Positive verification that promptfoo has actually passed.

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

**Text-representation normalization (two real false-positive reports).**
A fresh, genuinely current-checkout live Groq run was rejected by this
check immediately after passing 10/10 -- twice, on two different reported
root causes, both confirmed real:

1. (First report.) A theorized CRLF/LF asymmetry: Python's
   ``Path.read_text()`` applies universal-newline translation on every
   read, silently turning CRLF into LF, while a naive reading of
   promptfoo's ``fs.readFileSync(path, "utf8")`` suggested it would
   preserve on-disk CRLF verbatim. Reading promptfoo's actual
   ``.txt``-file loader (``processTxtFile``,
   ``dist/src/graders-*.js``, promptfoo 0.121.17) shows this is only
   *half* right: it does ``fs.readFileSync(path, "utf8").split(/\\r?\\n/)``
   then rejoins with ``"\\n"`` -- so promptfoo itself already neutralizes
   CRLF vs LF for a ``file://prompt.txt``-style ``.txt`` prompt before
   ``raw`` is ever recorded. CRLF canonicization here is still applied
   (harmless, and a legitimate defense for any prompt source that isn't
   loaded through this exact ``.txt`` code path), but it was not, by
   itself, the mechanism that produced the reported failure.
2. (Second report, the actual mechanism, found from a real artifact
   generated by the actual installed ``promptfoo`` binary against the
   actual ``promptfoo/prompt.txt``.) That same ``processTxtFile`` ends
   with ``const raw = buffer.join("\\n").trim()`` -- an unconditional
   ``.trim()`` that strips leading/trailing whitespace, most
   consequentially the trailing newline ``prompt.txt`` ends with on disk.
   A real captured run's ``results.prompts[0].raw`` was measured at 3234
   characters, not ending in ``\\n``; the same file read via
   ``Path.read_text()`` is 3235 characters, ending in ``\\n``. That
   single trailing character was the entire "drift" on a run that was
   never stale and never CRLF-affected -- it would reproduce identically
   on Linux or macOS, with no Windows/autocrlf involvement at all.

``_canonicalize_prompt_text`` mirrors both operations promptfoo's own
loader actually performs -- CRLF/CR collapse (harmless, defensive) then
``.strip()`` (the operation actually proven, by source inspection and by
a real captured artifact, to explain the reported failure) -- applied to
both sides before comparing. Nothing else is normalized: a real
difference anywhere in the interior of the prompt's words, structure, or
braces still fails this check exactly as before.
"""

from __future__ import annotations

import hashlib
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


def _canonicalize_prompt_text(text: str) -> str:
    r"""Mirror the two operations promptfoo's own ``.txt``-prompt loader performs.

    So this comparison judges the same thing promptfoo itself already
    decided the prompt's content is. Proven from promptfoo 0.121.17's
    actual installed source
    (``processTxtFile``, ``dist/src/graders-*.js``):
    ``fs.readFileSync(path, "utf8").split(/\\r?\\n/)`` followed by
    ``buffer.join("\\n").trim()``. Two representation differences follow
    directly from that, neither semantic:

    - CRLF/CR collapse to LF (from the split/rejoin) -- defensive here,
      since this specific ``.txt`` loader already performs it before
      ``raw`` is ever recorded, but not every prompt source promptfoo
      supports is guaranteed to.
    - Leading/trailing whitespace stripped (from ``.trim()``) -- this is
      the operation actually confirmed, against a real artifact generated
      by the real installed promptfoo binary against the real
      ``promptfoo/prompt.txt``, to explain a genuine false-positive
      rejection: the file ends in a trailing newline on disk (3235
      characters), promptfoo's recorded ``raw`` does not (3234
      characters) -- one trimmed character was the entire reported
      "drift" on an artifact that was never stale.

    Applying both to *both* sides here is safe and idempotent: promptfoo's
    own ``raw`` is already exactly what this produces, so re-applying it
    changes nothing on that side; the current ``prompt.txt`` read is what
    gets normalized to match. Nothing else -- no interior whitespace, no
    case-folding, no Unicode normalization -- is touched, so a genuine
    difference in the prompt's words, structure, or braces still fails
    this check exactly as before.
    """
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


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
        payload = json.loads(results_path.read_text(encoding="utf-8"))
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
        current_text = prompt_txt_path.read_text(encoding="utf-8")
        if recorded_raw is not None and _canonicalize_prompt_text(
            recorded_raw
        ) != _canonicalize_prompt_text(current_text):
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


def _first_difference(a: str, b: str) -> tuple[int, str, str] | None:
    """Index of the first character where ``a`` and ``b`` diverge, or ``None``.

    Also returns a short ``repr()`` window around it on each side. Never
    returns the strings' full content: callers of
    :func:`diagnose_prompt_drift` pass prompt-template text here, which
    contains no résumé/claim content (that lives in ``tests.yaml``'s
    ``evidence``/``statement`` vars, substituted only at Nunjucks render
    time, never present in the raw template this compares).
    """
    common = min(len(a), len(b))
    for i in range(common):
        if a[i] != b[i]:
            return i, repr(a[max(0, i - 20) : i + 20]), repr(b[max(0, i - 20) : i + 20])
    if len(a) != len(b):
        return common, repr(a[max(0, common - 20) : common + 20]), repr(
            b[max(0, common - 20) : common + 20]
        )
    return None


def diagnose_prompt_drift(
    prompt_version: str, results_dir: Path, *, provider_id: str
) -> str:
    """Report why verify_promptfoo_results' drift check would accept/reject an artifact.

    Uses the *same* ``_recorded_prompt_raw`` / ``_canonicalize_prompt_text``
    the real check uses, never a reimplementation of it, so this report
    can never disagree with what the real check actually does.

    Prints lengths, SHA-256 hashes (raw and canonicalized), BOM/trailing-
    newline/CRLF presence on each side, the first differing character
    index with a small ``repr()`` window around it, and the results file's
    own recorded prompt-array metadata (count, keys) -- deliberately never
    the full prompt or claim/evidence text, so this is safe to paste
    output from without exposing your résumé content or any secret.
    """
    lines: list[str] = []
    results_path = results_dir / f"{prompt_version}--{provider_id}.json"
    if not results_path.exists():
        return f"No results file at {results_path}"
    payload = json.loads(results_path.read_text(encoding="utf-8"))
    prompts = payload.get("results", {}).get("prompts", [])
    lines.append(f"results.prompts: {len(prompts)} entrie(s)")
    if prompts:
        lines.append(f"results.prompts[0] keys: {sorted(prompts[0].keys())}")
    recorded_raw = _recorded_prompt_raw(payload)
    lines.append(f"recorded raw: type={type(recorded_raw).__name__}")
    if recorded_raw is None:
        lines.append(
            "No results.prompts[0].raw string found -- drift check is skipped."
        )
        return "\n".join(lines)

    prompt_txt_path = results_dir.parent / "prompt.txt"
    if not prompt_txt_path.exists():
        lines.append(
            f"No sibling {prompt_txt_path} -- drift check is skipped "
            f"(nothing to compare recorded raw against)."
        )
        return "\n".join(lines)
    current_text = prompt_txt_path.read_text(encoding="utf-8")

    def _describe(label: str, text: str) -> None:
        lines.append(
            f"{label}: len={len(text)} "
            f"sha256={hashlib.sha256(text.encode('utf-8')).hexdigest()} "
            f"bom={text.startswith(chr(0xFEFF))} "
            f"trailing_newline={text.endswith(chr(10))} "
            f"has_crlf={chr(13) + chr(10) in text} "
            f"has_bare_cr={chr(13) in text and chr(13) + chr(10) not in text}"
        )

    _describe("recorded raw", recorded_raw)
    _describe("current prompt.txt", current_text)

    canon_recorded = _canonicalize_prompt_text(recorded_raw)
    canon_current = _canonicalize_prompt_text(current_text)
    _describe("recorded raw (canonicalized)", canon_recorded)
    _describe("current prompt.txt (canonicalized)", canon_current)

    if canon_recorded == canon_current:
        lines.append("MATCH after canonicalization -- drift check would PASS.")
        return "\n".join(lines)

    lines.append("MISMATCH after canonicalization -- drift check would FAIL.")
    diff = _first_difference(canon_recorded, canon_current)
    if diff is not None:
        index, window_a, window_b = diff
        end_marker = "<end of string>"
        codepoint_a = (
            hex(ord(canon_recorded[index]))
            if index < len(canon_recorded)
            else end_marker
        )
        codepoint_b = (
            hex(ord(canon_current[index]))
            if index < len(canon_current)
            else end_marker
        )
        lines.append(f"first differing index (canonicalized): {index}")
        lines.append(f"  recorded codepoint: {codepoint_a}, window: {window_a}")
        lines.append(f"  current  codepoint: {codepoint_b}, window: {window_b}")
    return "\n".join(lines)
