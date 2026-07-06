"""ADR-0042 / ADR-0043: Groq free-tier provider selection, wiring, and
failure modes -- including the truthfulness gate's verifier, which ADR-0043
moved from Anthropic-only to Groq-preferred on direct user instruction to
run the whole project at zero ongoing cost.

Every network call is mocked via ``httpx.MockTransport`` -- no real API
credits are ever spent running this suite, the same offline discipline as
every other real-network component in this project.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import httpx
import pytest

from career_agent.core.config import Settings
from career_agent.domain.ats_scoring import AtsGapReport, SurfaceableKeyword
from career_agent.domain.models import BasicsSection, MasterProfile, Provenance
from career_agent.llm import groq_client
from career_agent.llm.claim_verifier import AnthropicClaimVerifier
from career_agent.llm.content_drafter import AnthropicContentDrafter
from career_agent.llm.groq_claim_verifier import GroqClaimVerifier
from career_agent.llm.groq_client import (
    GroqCallError,
    extract_json_object,
    groq_chat_completion,
)
from career_agent.llm.groq_content_drafter import GroqContentDrafter
from career_agent.llm.groq_semantic_matcher import GroqSemanticKeywordMatcher
from career_agent.llm.providers import (
    NoLLMProviderConfiguredError,
    select_claim_verifier,
    select_content_drafter,
    select_semantic_matcher,
)
from career_agent.llm.semantic_matcher import AnthropicSemanticKeywordMatcher


def _opportunity():
    from career_agent.domain.models import Opportunity

    return Opportunity(
        id="opp-1",
        company_id="acme",
        canonical_company="acme.com",
        title="Software Engineer",
        source="ats_api",
        source_url="https://example.invalid/opp-1",
        provenance=Provenance(
            method="structured_api",
            reference="https://example.invalid/opp-1",
            extraction_confidence=1.0,
        ),
        description_raw="Backend role, Python, Docker.",
        discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _profile() -> MasterProfile:
    return MasterProfile(
        version="v1", basics=BasicsSection(name="Ada", email="ada@example.com")
    )


_RealAsyncClient = httpx.AsyncClient


def _mock_client(handler):
    """A one-shot httpx client wired to a synchronous handler function."""
    transport = httpx.MockTransport(handler)
    return lambda *args, **kwargs: _RealAsyncClient(transport=transport, **kwargs)


def _groq_response(content: str) -> httpx.Response:
    return httpx.Response(
        200, json={"choices": [{"message": {"content": content}}]}
    )


# --- groq_client.groq_chat_completion: the shared HTTP call ----------------


async def test_groq_call_returns_message_content(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer secret-key"
        body = json.loads(request.content)
        assert body["model"] == "llama-3.3-70b-versatile"
        assert body["messages"][0]["content"] == "hello"
        return _groq_response('{"ok": true}')

    monkeypatch.setattr(
        groq_client.httpx, "AsyncClient", _mock_client(handler)
    )
    text = await groq_chat_completion(
        api_key="secret-key",
        model="llama-3.3-70b-versatile",
        prompt="hello",
        max_tokens=100,
    )
    assert text == '{"ok": true}'


async def test_groq_call_omits_reasoning_params_when_not_given(monkeypatch):
    """Non-reasoning models (llama-3.3-70b-versatile) never see these keys --
    only a caller that explicitly asks for them (GroqClaimVerifier) does."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert "reasoning_effort" not in body
        assert "include_reasoning" not in body
        return _groq_response('{"ok": true}')

    monkeypatch.setattr(groq_client.httpx, "AsyncClient", _mock_client(handler))
    await groq_chat_completion(
        api_key="k", model="llama-3.3-70b-versatile", prompt="p", max_tokens=100
    )


async def test_groq_call_forwards_reasoning_params_when_given(monkeypatch):
    """Regression for the live-run truncation bug: reasoning_effort and
    include_reasoning must actually reach the request body when a caller
    (GroqClaimVerifier) supplies them -- a silent no-op here would look
    identical to the config that scored 0/10 on the real 12-case matrix."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["reasoning_effort"] == "low"
        assert body["include_reasoning"] is False
        return _groq_response('{"ok": true}')

    monkeypatch.setattr(groq_client.httpx, "AsyncClient", _mock_client(handler))
    await groq_chat_completion(
        api_key="k",
        model="openai/gpt-oss-120b",
        prompt="p",
        max_tokens=2000,
        reasoning_effort="low",
        include_reasoning=False,
    )


async def test_groq_call_raises_typed_error_on_http_failure(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    monkeypatch.setattr(
        groq_client.httpx, "AsyncClient", _mock_client(handler)
    )
    with pytest.raises(GroqCallError, match="Groq call failed"):
        await groq_chat_completion(
            api_key="k", model="m", prompt="p", max_tokens=10
        )


async def test_groq_call_raises_typed_error_on_malformed_shape(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    monkeypatch.setattr(
        groq_client.httpx, "AsyncClient", _mock_client(handler)
    )
    with pytest.raises(GroqCallError, match="unexpected response shape"):
        await groq_chat_completion(
            api_key="k", model="m", prompt="p", max_tokens=10
        )


async def test_groq_call_never_logs_the_api_key(monkeypatch, caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    monkeypatch.setattr(
        groq_client.httpx, "AsyncClient", _mock_client(handler)
    )
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(GroqCallError):
            await groq_chat_completion(
                api_key="super-secret-key",
                model="m",
                prompt="p",
                max_tokens=10,
            )
    assert "super-secret-key" not in caplog.text


# --- extract_json_object: the second live-run bug's fix ------------------


def test_extract_json_object_returns_pure_json_unchanged():
    text = '{"verified": true, "confidence": 1.0}'
    assert extract_json_object(text) == text


def test_extract_json_object_strips_a_reasoning_preamble():
    """The exact shape of the second live promptfoo run's output."""
    text = 'Thinking: blah blah blah\n{"verified": false, "confidence": 0.99}'
    assert extract_json_object(text) == '{"verified": false, "confidence": 0.99}'


def test_extract_json_object_raises_when_no_braces_at_all():
    with pytest.raises(ValueError, match="no JSON object found"):
        extract_json_object("just reasoning text, no JSON anywhere")


def test_extract_json_object_raises_when_only_a_closing_brace():
    with pytest.raises(ValueError, match="no JSON object found"):
        extract_json_object("text ending in a stray }")


# --- GroqContentDrafter: raises outward, same contract as Anthropic's ------


async def test_groq_content_drafter_parses_a_successful_draft(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert "reasoning_effort" not in body
        assert "include_reasoning" not in body
        return _groq_response(
            json.dumps({"work": [], "skills": ["Python"], "projects": []})
        )

    monkeypatch.setattr(
        groq_client.httpx, "AsyncClient", _mock_client(handler)
    )
    drafter = GroqContentDrafter(api_key="k")
    result = await drafter.draft(_opportunity(), _profile())
    assert result.skills == ["Python"]


async def test_groq_content_drafter_raises_on_malformed_json(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return _groq_response("not json")

    monkeypatch.setattr(
        groq_client.httpx, "AsyncClient", _mock_client(handler)
    )
    drafter = GroqContentDrafter(api_key="k")
    with pytest.raises(json.JSONDecodeError):
        await drafter.draft(_opportunity(), _profile())


async def test_groq_content_drafter_raises_on_network_failure_no_fallback(
    monkeypatch,
):
    """A Groq failure must propagate, not silently retry against Anthropic --
    there is no such fallback wired into this class at all."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    monkeypatch.setattr(
        groq_client.httpx, "AsyncClient", _mock_client(handler)
    )
    drafter = GroqContentDrafter(api_key="k")
    with pytest.raises(GroqCallError):
        await drafter.draft(_opportunity(), _profile())


# --- GroqSemanticKeywordMatcher: fails to [], same contract as Anthropic's -


async def test_groq_semantic_matcher_returns_claims_on_success(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return _groq_response(
            json.dumps([{"keyword": "Docker", "quoted_phrase": "containers"}])
        )

    monkeypatch.setattr(
        groq_client.httpx, "AsyncClient", _mock_client(handler)
    )
    matcher = GroqSemanticKeywordMatcher(api_key="k")
    claims = await matcher.propose_matches(["Docker"], "I use containers daily.")
    assert claims[0].keyword == "Docker"


async def test_groq_semantic_matcher_fails_open_to_empty_on_malformed_json(
    monkeypatch,
):
    def handler(request: httpx.Request) -> httpx.Response:
        return _groq_response("not json")

    monkeypatch.setattr(
        groq_client.httpx, "AsyncClient", _mock_client(handler)
    )
    matcher = GroqSemanticKeywordMatcher(api_key="k")
    assert await matcher.propose_matches(["Docker"], "text") == []


async def test_groq_semantic_matcher_fails_open_to_empty_on_timeout(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    monkeypatch.setattr(
        groq_client.httpx, "AsyncClient", _mock_client(handler)
    )
    matcher = GroqSemanticKeywordMatcher(api_key="k")
    assert await matcher.propose_matches(["Docker"], "text") == []


async def test_groq_semantic_matcher_short_circuits_on_no_missing_keywords():
    """No keywords -> no call at all (matches the Anthropic port's contract)."""
    matcher = GroqSemanticKeywordMatcher(api_key="k")
    assert await matcher.propose_matches([], "text") == []


def test_gap_report_still_structurally_genuine_gap_free():
    """Unrelated to the provider: confirms this change didn't touch the
    channel restriction the ATS gate's B1 case depends on."""
    report = AtsGapReport(
        surfaceable=[SurfaceableKeyword(keyword="Docker", profile_evidence="e")]
    )
    assert set(AtsGapReport.model_fields) == {"surfaceable"}
    assert report.surfaceable[0].keyword == "Docker"


# --- provider selection: Groq preferred, Anthropic fallback, no silent mix -


def test_select_content_drafter_prefers_groq_when_both_keys_set():
    settings = Settings(groq_api_key="g", anthropic_api_key="a")
    assert isinstance(select_content_drafter(settings), GroqContentDrafter)


def test_select_content_drafter_falls_back_to_anthropic_when_no_groq_key():
    settings = Settings(groq_api_key=None, anthropic_api_key="a")
    assert isinstance(select_content_drafter(settings), AnthropicContentDrafter)


def test_select_content_drafter_raises_typed_error_with_neither_key():
    settings = Settings(groq_api_key=None, anthropic_api_key=None)
    with pytest.raises(NoLLMProviderConfiguredError, match="GROQ_API_KEY"):
        select_content_drafter(settings)


def test_select_semantic_matcher_prefers_groq_when_both_keys_set():
    settings = Settings(groq_api_key="g", anthropic_api_key="a")
    assert isinstance(select_semantic_matcher(settings), GroqSemanticKeywordMatcher)


def test_select_semantic_matcher_falls_back_to_anthropic_when_no_groq_key():
    settings = Settings(groq_api_key=None, anthropic_api_key="a")
    assert isinstance(
        select_semantic_matcher(settings), AnthropicSemanticKeywordMatcher
    )


def test_select_semantic_matcher_is_none_with_neither_key():
    """None is a legitimate answer here -- the semantic layer is advisory
    only (ADR-0034); unlike the drafter, its absence isn't an error."""
    settings = Settings(groq_api_key=None, anthropic_api_key=None)
    assert select_semantic_matcher(settings) is None


def test_select_claim_verifier_prefers_groq_when_both_keys_set():
    """ADR-0043: unlike ADR-0042's original design, the truthfulness gate's
    verifier now prefers the free provider too -- compensated for by the
    provider-keyed promptfoo gate (test_promptfoo_gate.py), not by refusing
    to select Groq here."""
    settings = Settings(groq_api_key="g", anthropic_api_key="a")
    assert isinstance(select_claim_verifier(settings), GroqClaimVerifier)


def test_select_claim_verifier_falls_back_to_anthropic_when_no_groq_key():
    settings = Settings(groq_api_key=None, anthropic_api_key="a")
    assert isinstance(select_claim_verifier(settings), AnthropicClaimVerifier)


def test_select_claim_verifier_raises_typed_error_with_neither_key():
    settings = Settings(groq_api_key=None, anthropic_api_key=None)
    with pytest.raises(NoLLMProviderConfiguredError, match="GROQ_API_KEY"):
        select_claim_verifier(settings)


def test_groq_and_anthropic_claim_verifiers_carry_distinct_provider_ids():
    """The promptfoo gate keys results by this attribute -- if the two ever
    collided, a pass for one would silently authorize the other."""
    assert GroqClaimVerifier(api_key="k").provider_id == "groq"
    assert AnthropicClaimVerifier(api_key="k").provider_id == "anthropic"
    assert (
        GroqClaimVerifier(api_key="k").provider_id
        != AnthropicClaimVerifier(api_key="k").provider_id
    )


def test_groq_and_anthropic_claim_verifiers_share_the_same_prompt_version():
    """Only the provider changed, not the prompt -- so no new prompt-version
    baseline is needed, only a new (existing) provider-keyed promptfoo run."""
    assert (
        GroqClaimVerifier(api_key="k").prompt_version
        == AnthropicClaimVerifier(api_key="k").prompt_version
    )


# --- GroqClaimVerifier: fail-closed, same contract as Anthropic's ----------


async def test_groq_claim_verifier_parses_a_successful_verdict(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "openai/gpt-oss-120b"
        return _groq_response(
            json.dumps(
                {
                    "verified": True,
                    "confidence": 0.95,
                    "category": None,
                    "detail": "supported",
                }
            )
        )

    monkeypatch.setattr(groq_client.httpx, "AsyncClient", _mock_client(handler))
    verifier = GroqClaimVerifier(api_key="k")
    verdict = await verifier.verify_claim("I know Docker.", "Used Docker daily.")
    assert verdict.verified is True
    assert verdict.confidence == 0.95


async def test_groq_claim_verifier_sends_the_reasoning_truncation_fix(monkeypatch):
    """Regression for the live 0/10 promptfoo run: max_tokens=300 with no
    reasoning_effort/include_reasoning let gpt-oss-120b's hidden
    chain-of-thought consume the whole budget before any JSON was emitted.
    Pins the exact fix so a future edit can't silently regress it back to
    the config that failed live -- must also stay in sync with
    promptfoo/promptfooconfig.groq.yaml, which this test cannot check."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["max_tokens"] >= 2000
        assert body["reasoning_effort"] == "low"
        assert body["include_reasoning"] is False
        return _groq_response(
            json.dumps(
                {"verified": True, "confidence": 1.0, "category": None, "detail": "x"}
            )
        )

    monkeypatch.setattr(groq_client.httpx, "AsyncClient", _mock_client(handler))
    await GroqClaimVerifier(api_key="k").verify_claim("claim", "evidence")


async def test_groq_claim_verifier_raises_on_malformed_json(monkeypatch):
    """Fail-closed, never a fabricated verdict -- identical contract to
    AnthropicClaimVerifier. No '{'/'}' at all -> extraction itself fails
    (ValueError), not json.loads -- both are fail-closed either way."""

    def handler(request: httpx.Request) -> httpx.Response:
        return _groq_response("not json")

    monkeypatch.setattr(groq_client.httpx, "AsyncClient", _mock_client(handler))
    verifier = GroqClaimVerifier(api_key="k")
    with pytest.raises(ValueError, match="no JSON object found"):
        await verifier.verify_claim("claim", "evidence")


async def test_groq_claim_verifier_extracts_json_past_a_reasoning_preamble(
    monkeypatch,
):
    """Regression for the second live-run bug: gpt-oss-120b prepends visible
    reasoning to its answer even with include_reasoning=False. The verdict
    must still parse correctly from "Thinking: ...\\n{json}", the exact
    shape the live promptfoo run returned on every one of its 10 cases."""

    def handler(request: httpx.Request) -> httpx.Response:
        return _groq_response(
            'Thinking: We need to check claim. Evidence says X. So verified '
            'false, category skill_not_found.\n'
            + json.dumps(
                {
                    "verified": False,
                    "confidence": 0.99,
                    "category": "skill_not_found",
                    "detail": "AWS is not in evidence",
                }
            )
        )

    monkeypatch.setattr(groq_client.httpx, "AsyncClient", _mock_client(handler))
    verdict = await GroqClaimVerifier(api_key="k").verify_claim("AWS", "Python only")
    assert verdict.verified is False
    assert verdict.category == "skill_not_found"


async def test_groq_claim_verifier_raises_on_network_failure_no_fallback(
    monkeypatch,
):
    """A Groq failure must propagate, never silently retry against a paid
    Anthropic call -- there is no such fallback wired into this class."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    monkeypatch.setattr(groq_client.httpx, "AsyncClient", _mock_client(handler))
    verifier = GroqClaimVerifier(api_key="k")
    with pytest.raises(GroqCallError):
        await verifier.verify_claim("claim", "evidence")
