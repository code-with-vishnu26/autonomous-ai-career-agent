"""Enforces domain/'s zero-I/O contract (see career_agent/domain/__init__.py).

This is the enforceable version of "domain must never import a networking
client, a database driver, a browser-automation library, or an LLM SDK": it
parses every module under ``career_agent.domain`` and asserts every top-level
import comes from an allowlist, instead of merely asserting it in a docstring.
"""

from __future__ import annotations

import ast
import importlib
import pkgutil
from pathlib import Path

import career_agent.domain as domain_pkg

ALLOWED_TOP_LEVEL_IMPORTS = {
    # standard library
    "__future__",
    "datetime",
    "typing",
    "enum",
    "uuid",
    "dataclasses",
    # the one third-party dependency domain is allowed: Pydantic
    "pydantic",
    # domain may import from itself
    "career_agent",
}


def _domain_module_paths() -> list[Path]:
    package_dir = Path(domain_pkg.__file__).parent
    return sorted(package_dir.rglob("*.py"))


def _top_level_imports(source: str) -> set[str]:
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                modules.add(node.module.split(".")[0])
    return modules


def test_domain_files_only_import_allowed_modules() -> None:
    """Every module under domain/ imports only stdlib, pydantic, or itself."""
    offenders: dict[str, set[str]] = {}
    for path in _domain_module_paths():
        imports = _top_level_imports(path.read_text())
        disallowed = imports - ALLOWED_TOP_LEVEL_IMPORTS
        if disallowed:
            offenders[str(path)] = disallowed
    assert not offenders, f"domain/ imported disallowed modules: {offenders}"


def test_domain_subpackages_only_reference_career_agent_domain() -> None:
    """No domain module imports from career_agent.core/agents/plugins/etc."""
    forbidden_subpackages = {
        "career_agent.core",
        "career_agent.agents",
        "career_agent.plugins",
        "career_agent.llm",
        "career_agent.storage",
        "career_agent.integrations",
    }
    offenders: dict[str, set[str]] = {}
    for path in _domain_module_paths():
        tree = ast.parse(path.read_text())
        referenced: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                referenced.add(node.module)
        hit = {
            mod
            for mod in referenced
            if any(mod.startswith(forbidden) for forbidden in forbidden_subpackages)
        }
        if hit:
            offenders[str(path)] = hit
    assert not offenders, f"domain/ referenced non-domain layers: {offenders}"


def test_importing_domain_does_not_pull_in_io_libraries() -> None:
    """Belt-and-suspenders: after importing domain, forbidden modules are absent.

    Import-time side effects (rather than just static analysis) are what
    would actually leak an I/O dependency into every consumer of domain/, so
    this checks the real, post-import module table too.
    """
    import sys

    for _finder, name, _ispkg in pkgutil.walk_packages(
        domain_pkg.__path__, prefix="career_agent.domain."
    ):
        importlib.import_module(name)

    forbidden_loaded = {
        mod
        for mod in sys.modules
        if mod.split(".")[0]
        in {"httpx", "playwright", "anthropic", "sqlite3", "langgraph", "openpyxl"}
    }
    assert not forbidden_loaded, (
        f"importing career_agent.domain pulled in I/O libraries: {forbidden_loaded}"
    )
