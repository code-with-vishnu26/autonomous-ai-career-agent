"""``career-agent verify-promptfoo``: a zero-cost, offline entry point that
directly calls the same ``verify_promptfoo_results`` gate ``apply`` uses,
against a real local results artifact, without needing that provider's API
key configured just to check it.
"""

from __future__ import annotations

import json
from pathlib import Path

from career_agent.cli import main, run_verify_promptfoo_command
from career_agent.llm.prompts import TRUTHFULNESS_GATE_PROMPT_VERSION


def _write_clean_results(
    dir_: Path, provider_id: str, provider_recorded_id: str
) -> None:
    dir_.mkdir(parents=True, exist_ok=True)
    payload = {
        "results": {"stats": {"successes": 10, "failures": 0, "errors": 0}},
        "config": {"providers": [{"id": provider_recorded_id}]},
    }
    path = dir_ / f"{TRUTHFULNESS_GATE_PROMPT_VERSION}--{provider_id}.json"
    path.write_text(json.dumps(payload))


def test_passes_on_a_real_clean_groq_artifact(tmp_path: Path) -> None:
    _write_clean_results(tmp_path, "groq", "openai:chat:openai/gpt-oss-120b")
    assert run_verify_promptfoo_command("groq", tmp_path) == 0


def test_fails_when_no_artifact_exists(tmp_path: Path) -> None:
    assert run_verify_promptfoo_command("groq", tmp_path) == 1


def test_fails_on_a_failed_run(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    payload = {
        "results": {"stats": {"successes": 8, "failures": 2, "errors": 0}},
        "config": {"providers": [{"id": "openai:chat:openai/gpt-oss-120b"}]},
    }
    path = tmp_path / f"{TRUTHFULNESS_GATE_PROMPT_VERSION}--groq.json"
    path.write_text(json.dumps(payload))
    assert run_verify_promptfoo_command("groq", tmp_path) == 1


def test_wired_into_the_real_cli_as_a_subcommand(tmp_path: Path) -> None:
    """Proves ``verify-promptfoo`` is reachable through the actual
    ``career-agent`` entry point (argparse subparser + dispatch), not just
    as a bare function."""
    _write_clean_results(tmp_path, "groq", "openai:chat:openai/gpt-oss-120b")
    try:
        main(["verify-promptfoo", "--provider", "groq", "--results-dir", str(tmp_path)])
    except SystemExit as exc:
        assert exc.code == 0
    else:
        raise AssertionError(
            "main() should always raise SystemExit for a known command"
        )
