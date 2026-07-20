"""Phase 72 (ADR-0090): curated taxonomy + optional LLM RoleExpander fallback."""

from __future__ import annotations

from career_agent.agents.research.role_expansion import (
    suggest_related_terms_for_unknown_role,
)


class _FakeExpander:
    def __init__(self, suggestions: list[str] | None = None, *, fail: bool = False):
        self._suggestions = suggestions or []
        self._fail = fail
        self.calls: list[str] = []

    async def suggest_related_roles(self, role_query: str) -> list[str]:
        self.calls.append(role_query)
        if self._fail:
            raise RuntimeError("simulated network failure")
        return self._suggestions


async def test_known_role_never_calls_the_llm_expander() -> None:
    expander = _FakeExpander(["ignored"])
    terms = await suggest_related_terms_for_unknown_role(
        "Software Developer", expander
    )
    assert terms == frozenset()
    assert expander.calls == []


async def test_unknown_role_with_no_expander_returns_empty() -> None:
    terms = await suggest_related_terms_for_unknown_role(
        "Professional Dog Walker", None
    )
    assert terms == frozenset()


async def test_unknown_role_calls_the_expander_and_normalizes_terms() -> None:
    expander = _FakeExpander(["Dog Trainer", " Pet Sitter ", ""])
    terms = await suggest_related_terms_for_unknown_role(
        "Professional Dog Walker", expander
    )
    assert terms == frozenset({"dog trainer", "pet sitter"})
    assert expander.calls == ["Professional Dog Walker"]


async def test_expander_failure_degrades_to_empty_not_an_exception() -> None:
    expander = _FakeExpander(fail=True)
    terms = await suggest_related_terms_for_unknown_role(
        "Professional Dog Walker", expander
    )
    assert terms == frozenset()
