"""Phase 1 smoke tests: the package imports and the scaffolding is coherent."""

from __future__ import annotations

import importlib

import career_agent


def test_package_has_version() -> None:
    """The top-level package exposes a semantic version string."""
    assert isinstance(career_agent.__version__, str)
    assert career_agent.__version__.count(".") == 2


def test_subpackages_import() -> None:
    """Every scaffolded subpackage imports cleanly."""
    for name in (
        "career_agent.core",
        "career_agent.agents",
        "career_agent.agents.planner",
        "career_agent.agents.discovery",
        "career_agent.agents.resume",
        "career_agent.agents.apply",
        "career_agent.agents.learning",
        "career_agent.plugins",
        "career_agent.plugins.ats",
        "career_agent.plugins.sources",
        "career_agent.plugins.search",
        "career_agent.llm",
        "career_agent.storage",
        "career_agent.integrations",
    ):
        assert importlib.import_module(name) is not None


def test_cli_entrypoint_runs(capsys) -> None:
    """The placeholder CLI entry point executes and prints a banner."""
    from career_agent.cli import main

    main()
    out = capsys.readouterr().out
    assert "Autonomous AI Career Agent" in out
