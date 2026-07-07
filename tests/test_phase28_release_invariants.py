"""Phase 28: the release-invariant contract (ADR-0054).

A single consolidated place asserting the cross-cutting release invariants
that are not otherwise pinned as one contract. Per-component behavior is
proven by the phase suites (referenced in ADR-0054's invariant table); this
file pins the *release-gate* properties: no external submission is
reachable, the truthfulness release gate is enforced offline, the network
guard is active, and no machine-local artifact is required.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import career_agent.cli as cli_module
from career_agent.llm.promptfoo_gate import (
    PromptfooNotValidatedError,
    verify_promptfoo_results,
)


# I16 / I74-78: no external submission path is reachable from the CLI.
def test_no_external_submission_is_reachable_from_the_cli() -> None:
    source = inspect.getsource(cli_module)
    # The composition root constructs no concrete Applicator and calls no
    # submit/prepare -- every Applicator mention is documentation.
    for forbidden in (
        "TieredApplicator(",
        "BrowserApplicator(",
        "EmailApplicator(",
        "SubmissionPipeline(",
        ".submit(",
        ".prepare(",
    ):
        assert forbidden not in source, f"cli.py contains {forbidden!r}"


# I11: the truthfulness release gate blocks a required live-verifier path
# when validation is missing -- proven offline, no network.
def test_missing_promptfoo_artifact_blocks_the_gate(tmp_path: Path) -> None:
    with pytest.raises(PromptfooNotValidatedError):
        verify_promptfoo_results(
            "truthfulness-gate-v2", tmp_path / "empty", provider_id="groq"
        )


def test_malformed_promptfoo_artifact_blocks_the_gate(tmp_path: Path) -> None:
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "truthfulness-gate-v2--groq.json").write_text(
        "{ not valid json", encoding="utf-8"
    )
    with pytest.raises(PromptfooNotValidatedError):
        verify_promptfoo_results(
            "truthfulness-gate-v2", results_dir, provider_id="groq"
        )


# I11 (apply/auto ordering): both real entry points verify promptfoo before
# ever using the live verifier -- structural proof over the source.
def test_apply_and_auto_gate_before_constructing_the_live_verifier() -> None:
    for fn_name in ("run_apply_command", "run_auto_cli_command"):
        src = inspect.getsource(getattr(cli_module, fn_name))
        assert "select_claim_verifier" in src
        assert "verify_promptfoo_results" in src
        # The verify call textually precedes the generator/gate construction.
        assert src.index("verify_promptfoo_results") < src.index(
            "LLMResumeGenerator"
        ), f"{fn_name}: promptfoo gate must run before verifier construction"


# I12: the autouse network guard blocks real provider hosts while leaving
# httpx.MockTransport usable.
async def test_network_guard_blocks_real_provider_but_allows_mock_transport() -> None:
    import httpx

    # A real (non-mock) transport to a blocked host must raise.
    async with httpx.AsyncClient() as client:
        with pytest.raises(RuntimeError):
            await client.get("https://api.groq.com/v1/models")

    # A MockTransport client to the same host is allowed (offline fake path).
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get("https://api.groq.com/v1/models")
    assert response.status_code == 200


# I17: an ordinary isolated unit test needs no machine-local promptfoo
# artifact -- the default results dir is overridable and the gate is offline.
def test_verify_promptfoo_results_signature_supports_isolated_dir() -> None:
    params = list(inspect.signature(verify_promptfoo_results).parameters)
    # (prompt_version, results_dir, *, provider_id) -- an explicit dir arg,
    # so a test never has to depend on the developer's real artifact.
    assert params[1] == "results_dir"


# I15: the journal has no event that asserts external submission success --
# a journal record is never treated as proof an application was sent.
def test_journal_vocabulary_has_no_external_submission_success_event() -> None:
    e2e = inspect.getsource(cli_module)
    # cli emits RUN_*/TAILORING_*/EXECUTION_REFUSED/APPLICATION_PREPARED etc.,
    # never an "APPLICATION_SUBMITTED"/"EXTERNAL_ACTION_CONFIRMED" event,
    # because no submission occurs.
    assert "APPLICATION_SUBMITTED" not in e2e
    assert "EXTERNAL_ACTION_CONFIRMED" not in e2e
