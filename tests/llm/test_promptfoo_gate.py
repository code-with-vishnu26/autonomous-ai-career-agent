"""ADR-0016 / ADR-0026 / ADR-0043: promptfoo validation is a fact the system
checks against a results artifact, never a claim the caller asserts -- keyed
to provider as well as prompt version, so a pass for one ClaimVerifier
implementation can never authorize another.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from career_agent.llm.promptfoo_gate import (
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
) -> None:
    dir_.mkdir(parents=True, exist_ok=True)
    payload = {"results": {"stats": {"successes": successes, "failures": failures}}}
    (dir_ / f"{prompt_version}--{provider_id}.json").write_text(json.dumps(payload))


def test_raises_when_no_results_file_exists(tmp_path: Path) -> None:
    with pytest.raises(PromptfooNotValidatedError, match="No promptfoo results"):
        verify_promptfoo_results(
            "truthfulness-gate-v1", tmp_path, provider_id="anthropic"
        )


def test_passes_silently_when_all_cases_passed(tmp_path: Path) -> None:
    _write_results(
        tmp_path, "truthfulness-gate-v1", "anthropic", successes=12, failures=0
    )
    verify_promptfoo_results(
        "truthfulness-gate-v1", tmp_path, provider_id="anthropic"
    )  # does not raise


def test_raises_when_any_case_failed(tmp_path: Path) -> None:
    _write_results(
        tmp_path, "truthfulness-gate-v1", "anthropic", successes=11, failures=1
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
    with pytest.raises(PromptfooNotValidatedError):
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
            results_dir, "truthfulness-gate-v1", "anthropic", successes=12, failures=0
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
            results_dir, "truthfulness-gate-v1", "anthropic", successes=12, failures=0
        )
        with pytest.raises(PromptfooNotValidatedError, match="provider 'groq'"):
            verify_promptfoo_results(
                "truthfulness-gate-v1", results_dir, provider_id="groq"
            )
