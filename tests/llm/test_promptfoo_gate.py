"""ADR-0016 / ADR-0026 / ADR-0043 / ADR-0044: promptfoo validation is a fact
the system checks against a results artifact, never a claim the caller
asserts -- keyed to provider and prompt version by filename, and (ADR-0044)
cross-checked against the file's own recorded stats and provider id, so
neither a partial run, a provider-side error, nor a misplaced results file
can be mistaken for a complete, clean pass.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from career_agent.llm.promptfoo_gate import (
    _EXPECTED_CASE_COUNT,
    _EXPECTED_PROVIDER_IDS,
    PromptfooNotValidatedError,
    verify_promptfoo_results,
)


def _write_results(
    dir_: Path,
    prompt_version: str,
    provider_id: str,
    *,
    successes: int,
    failures: int,
    errors: int = 0,
    recorded_provider: str | None = None,
    recorded_prompt_raw: str | None = None,
) -> None:
    """Write a results file shaped like a real promptfoo output.

    ``recorded_provider`` defaults to the *correct* id for ``provider_id``
    (from ``_EXPECTED_PROVIDER_IDS``) so tests that aren't specifically
    about provider mismatch don't have to think about it; pass an explicit
    (wrong) value to test that check. ``recorded_prompt_raw``, if given,
    populates ``results.prompts[0].raw`` the way a real promptfoo run does;
    omitted by default so existing tests (no sibling ``prompt.txt``) are
    unaffected by the drift check, which is skipped when that field is
    absent.
    """
    dir_.mkdir(parents=True, exist_ok=True)
    provider = recorded_provider or _EXPECTED_PROVIDER_IDS[provider_id]
    results: dict[str, object] = {
        "stats": {
            "successes": successes,
            "failures": failures,
            "errors": errors,
        }
    }
    if recorded_prompt_raw is not None:
        results["prompts"] = [{"raw": recorded_prompt_raw}]
    payload = {
        "results": results,
        "config": {"providers": [{"id": provider, "config": {}}]},
    }
    (dir_ / f"{prompt_version}--{provider_id}.json").write_text(json.dumps(payload))


def test_expected_case_count_matches_the_real_tests_yaml_file() -> None:
    """Pins _EXPECTED_CASE_COUNT to the actual promptfoo/tests.yaml case
    count, not just to itself -- every other test in this file imports the
    constant directly, which would pass even if the constant silently drifted
    out of sync with the real matrix. This is the one test that would catch
    that drift."""
    tests_yaml = (
        Path(__file__).resolve().parents[2] / "promptfoo" / "tests.yaml"
    ).read_text()
    real_case_count = tests_yaml.count("\n- description:")
    assert _EXPECTED_CASE_COUNT == real_case_count


def test_raises_when_no_results_file_exists(tmp_path: Path) -> None:
    with pytest.raises(PromptfooNotValidatedError, match="No promptfoo results"):
        verify_promptfoo_results(
            "truthfulness-gate-v1", tmp_path, provider_id="anthropic"
        )


def test_passes_silently_on_a_complete_clean_run(tmp_path: Path) -> None:
    """The exact accept condition: every current-matrix case passed, zero
    failures, zero errors, correctly-recorded provider."""
    _write_results(
        tmp_path,
        "truthfulness-gate-v1",
        "anthropic",
        successes=_EXPECTED_CASE_COUNT,
        failures=0,
    )
    verify_promptfoo_results(
        "truthfulness-gate-v1", tmp_path, provider_id="anthropic"
    )  # does not raise


def test_raises_when_any_case_failed(tmp_path: Path) -> None:
    _write_results(
        tmp_path,
        "truthfulness-gate-v1",
        "anthropic",
        successes=_EXPECTED_CASE_COUNT - 1,
        failures=1,
    )
    with pytest.raises(PromptfooNotValidatedError, match="1 failing"):
        verify_promptfoo_results(
            "truthfulness-gate-v1", tmp_path, provider_id="anthropic"
        )


def test_raises_when_zero_successes_even_with_zero_failures(tmp_path: Path) -> None:
    """An empty/no-op run must not count as a pass."""
    _write_results(
        tmp_path, "truthfulness-gate-v1", "anthropic", successes=0, failures=0
    )
    with pytest.raises(PromptfooNotValidatedError, match="expected exactly"):
        verify_promptfoo_results(
            "truthfulness-gate-v1", tmp_path, provider_id="anthropic"
        )


def test_raises_on_malformed_json_rather_than_crashing(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "truthfulness-gate-v1--anthropic.json").write_text("not valid json{{{")
    with pytest.raises(PromptfooNotValidatedError, match="could not be read"):
        verify_promptfoo_results(
            "truthfulness-gate-v1", tmp_path, provider_id="anthropic"
        )


def test_raises_on_unexpected_json_shape(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"unexpected": True})
    (tmp_path / "truthfulness-gate-v1--anthropic.json").write_text(payload)
    with pytest.raises(PromptfooNotValidatedError, match="could not be read"):
        verify_promptfoo_results(
            "truthfulness-gate-v1", tmp_path, provider_id="anthropic"
        )


def test_a_stale_prompt_version_is_not_covered_by_an_old_pass() -> None:
    """The load-bearing test: results tied to a different (old) prompt
    version must never satisfy a check for the current one -- proven by
    filename, not by the caller's say-so."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        results_dir = Path(tmp)
        _write_results(
            results_dir,
            "truthfulness-gate-v1",
            "anthropic",
            successes=_EXPECTED_CASE_COUNT,
            failures=0,
        )
        with pytest.raises(PromptfooNotValidatedError):
            verify_promptfoo_results(
                "truthfulness-gate-v2", results_dir, provider_id="anthropic"
            )


def test_a_pass_for_one_provider_never_authorizes_another() -> None:
    """ADR-0043's load-bearing test: an Anthropic pass must never satisfy a
    check for the Groq provider (or vice versa) -- the exact failure mode
    that motivated keying the results filename to provider_id at all."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        results_dir = Path(tmp)
        _write_results(
            results_dir,
            "truthfulness-gate-v1",
            "anthropic",
            successes=_EXPECTED_CASE_COUNT,
            failures=0,
        )
        with pytest.raises(PromptfooNotValidatedError, match="provider 'groq'"):
            verify_promptfoo_results(
                "truthfulness-gate-v1", results_dir, provider_id="groq"
            )


def test_a_real_0_of_10_groq_run_cannot_unlock_the_verifier(tmp_path: Path) -> None:
    """The exact shape of a real live run against the pre-fix Groq config
    (max_tokens=300, no reasoning_effort/include_reasoning): 0 successes,
    10 failures, 0 errors. Written to disk at the real path
    verify_promptfoo_results checks, it must refuse -- confirming that this
    specific failed artifact can never be mistaken for a pass, regardless
    of how it got there."""
    _write_results(tmp_path, "truthfulness-gate-v1", "groq", successes=0, failures=10)
    with pytest.raises(PromptfooNotValidatedError, match="10 failing"):
        verify_promptfoo_results(
            "truthfulness-gate-v1", tmp_path, provider_id="groq"
        )


# ---------------------------------------------------------------------------
# ADR-0044: errors, expected-count, and provider-id hardening
# ---------------------------------------------------------------------------


def test_partial_run_with_remaining_cases_absent_is_rejected(tmp_path: Path) -> None:
    """1 success, 0 failures, but only 1 of _EXPECTED_CASE_COUNT cases ever
    ran -- must not pass merely because nothing that DID run failed."""
    _write_results(tmp_path, "truthfulness-gate-v2", "groq", successes=1, failures=0)
    with pytest.raises(PromptfooNotValidatedError, match="expected exactly"):
        verify_promptfoo_results(
            "truthfulness-gate-v2", tmp_path, provider_id="groq"
        )


def test_nine_success_zero_failures_one_error_is_rejected(tmp_path: Path) -> None:
    """The original bug this hardening closes: errors were never checked at
    all, so a run one case short of complete, with a provider-side error
    instead of a judged failure, would have silently passed before."""
    _write_results(
        tmp_path,
        "truthfulness-gate-v2",
        "groq",
        successes=_EXPECTED_CASE_COUNT - 1,
        failures=0,
        errors=1,
    )
    with pytest.raises(PromptfooNotValidatedError, match="1 error"):
        verify_promptfoo_results(
            "truthfulness-gate-v2", tmp_path, provider_id="groq"
        )


def test_seven_success_two_failures_one_error_is_rejected(tmp_path: Path) -> None:
    """The exact shape of the real truthfulness-gate-v2 live Groq run this
    ADR was written in response to: 7 passed, 2 failed, 1 error. Must
    reject on both the failures and the errors independently."""
    _write_results(
        tmp_path,
        "truthfulness-gate-v2",
        "groq",
        successes=7,
        failures=2,
        errors=1,
    )
    with pytest.raises(PromptfooNotValidatedError) as excinfo:
        verify_promptfoo_results(
            "truthfulness-gate-v2", tmp_path, provider_id="groq"
        )
    assert "2 failing" in str(excinfo.value)
    assert "1 error" in str(excinfo.value)


def test_expected_case_count_mismatch_is_rejected_even_with_zero_failures(
    tmp_path: Path,
) -> None:
    """More successes than the current matrix has cases is just as wrong as
    fewer -- the count must match exactly, not merely be non-zero."""
    _write_results(
        tmp_path,
        "truthfulness-gate-v2",
        "groq",
        successes=_EXPECTED_CASE_COUNT + 1,
        failures=0,
    )
    with pytest.raises(PromptfooNotValidatedError, match="expected exactly"):
        verify_promptfoo_results(
            "truthfulness-gate-v2", tmp_path, provider_id="groq"
        )


def test_missing_stats_key_entirely_is_rejected(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    payload = {"results": {}, "config": {"providers": []}}
    (tmp_path / "truthfulness-gate-v2--groq.json").write_text(json.dumps(payload))
    with pytest.raises(PromptfooNotValidatedError, match="could not be read"):
        verify_promptfoo_results(
            "truthfulness-gate-v2", tmp_path, provider_id="groq"
        )


def test_malformed_stats_values_are_rejected(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    payload = {
        "results": {
            "stats": {"successes": "not-a-number", "failures": 0, "errors": 0}
        },
        "config": {"providers": [{"id": "openai:chat:openai/gpt-oss-120b"}]},
    }
    (tmp_path / "truthfulness-gate-v2--groq.json").write_text(json.dumps(payload))
    with pytest.raises(PromptfooNotValidatedError, match="could not be read"):
        verify_promptfoo_results(
            "truthfulness-gate-v2", tmp_path, provider_id="groq"
        )


def test_wrong_recorded_provider_is_rejected_even_with_a_clean_pass(
    tmp_path: Path,
) -> None:
    """A results file renamed/misplaced to look like a groq pass, but whose
    own recorded provider config says otherwise, must not unlock anything
    -- the filename alone is not sufficient attribution."""
    _write_results(
        tmp_path,
        "truthfulness-gate-v2",
        "groq",
        successes=_EXPECTED_CASE_COUNT,
        failures=0,
        recorded_provider="anthropic:messages:claude-opus-4-8",
    )
    with pytest.raises(PromptfooNotValidatedError, match="recorded provider"):
        verify_promptfoo_results(
            "truthfulness-gate-v2", tmp_path, provider_id="groq"
        )


def test_exact_complete_clean_run_is_accepted(tmp_path: Path) -> None:
    """The one shape that should succeed: full case count, zero failures,
    zero errors, correctly-attributed provider."""
    _write_results(
        tmp_path,
        "truthfulness-gate-v2",
        "groq",
        successes=_EXPECTED_CASE_COUNT,
        failures=0,
        errors=0,
    )
    verify_promptfoo_results(
        "truthfulness-gate-v2", tmp_path, provider_id="groq"
    )  # does not raise


# ---------------------------------------------------------------------------
# Prompt-content drift check (integrity-against-drift only, best-effort;
# see promptfoo_gate.py's module docstring for what this does and does not
# prove -- it is not a defense against deliberate fabrication).
# ---------------------------------------------------------------------------


def test_prompt_drift_check_is_skipped_when_no_sibling_prompt_txt_exists(
    tmp_path: Path,
) -> None:
    """Every other test in this file relies on exactly this: a bare
    ``tmp_path`` results dir with no sibling ``prompt.txt`` must not be
    affected by the drift check at all, clean run or not."""
    _write_results(
        tmp_path,
        "truthfulness-gate-v2",
        "groq",
        successes=_EXPECTED_CASE_COUNT,
        failures=0,
        recorded_prompt_raw="whatever text, never compared",
    )
    verify_promptfoo_results(
        "truthfulness-gate-v2", tmp_path, provider_id="groq"
    )  # does not raise -- no promptfoo/prompt.txt sibling to compare against


def test_prompt_drift_check_passes_when_recorded_text_matches(
    tmp_path: Path,
) -> None:
    results_dir = tmp_path / "results"
    (tmp_path / "prompt.txt").write_text("CLAIM: {{statement}}\n")
    _write_results(
        results_dir,
        "truthfulness-gate-v2",
        "groq",
        successes=_EXPECTED_CASE_COUNT,
        failures=0,
        recorded_prompt_raw="CLAIM: {{statement}}\n",
    )
    verify_promptfoo_results(
        "truthfulness-gate-v2", results_dir, provider_id="groq"
    )  # does not raise -- recorded and current prompt text match exactly


def test_prompt_drift_check_ignores_crlf_vs_lf_line_endings(tmp_path: Path) -> None:
    """The exact false positive found from a real fresh 10/10/0 Groq run:
    promptfoo (Node) records prompt.txt's raw bytes with whatever line
    endings are physically on disk, while Python's Path.read_text() always
    translates CRLF to LF on read -- so a checkout with CRLF line endings
    (e.g. Windows git with core.autocrlf=true; this repo ships no
    .gitattributes to prevent that) made a genuinely fresh, unmodified
    prompt look like drift. Only the newline convention differs here, not
    the prompt's content."""
    results_dir = tmp_path / "results"
    lf_text = "CLAIM: {{statement}}\nEVIDENCE: {{evidence}}\n"
    (tmp_path / "prompt.txt").write_text(lf_text)
    _write_results(
        results_dir,
        "truthfulness-gate-v2",
        "groq",
        successes=_EXPECTED_CASE_COUNT,
        failures=0,
        recorded_prompt_raw=lf_text.replace("\n", "\r\n"),
    )
    verify_promptfoo_results(
        "truthfulness-gate-v2", results_dir, provider_id="groq"
    )  # does not raise -- CRLF vs LF is not real drift


def test_prompt_drift_check_rejects_a_mismatch(tmp_path: Path) -> None:
    """The results file proves a pass against a prompt that isn't the one
    currently on disk -- a stale/since-edited prompt.txt, not a fresh run
    against the current text."""
    results_dir = tmp_path / "results"
    (tmp_path / "prompt.txt").write_text("CLAIM: {{statement}}\n")
    _write_results(
        results_dir,
        "truthfulness-gate-v2",
        "groq",
        successes=_EXPECTED_CASE_COUNT,
        failures=0,
        recorded_prompt_raw="an old, since-changed prompt text\n",
    )
    with pytest.raises(PromptfooNotValidatedError, match="does not match"):
        verify_promptfoo_results(
            "truthfulness-gate-v2", results_dir, provider_id="groq"
        )
