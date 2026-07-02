"""Enforces domain/'s zero-I/O contract (see career_agent/domain/__init__.py).

This is the enforceable version of "domain must never import a networking
client, a database driver, a browser-automation library, or an LLM SDK": it
parses every module under ``career_agent.domain`` and asserts every top-level
import comes from an allowlist, instead of merely asserting it in a docstring.
"""

from __future__ import annotations

import ast
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
    "hashlib",
    "re",
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
    this checks the real, post-import module table too -- in a fresh
    subprocess, not this test process. Phase 7b3 added the first tests in
    this suite that genuinely import a forbidden library (real Playwright,
    driven against a local fixture) for a *different* module; checking
    ``sys.modules`` in-process would make this test's result depend on
    unrelated test collection order rather than on what importing ``domain``
    itself does, which is the one thing this test exists to verify.
    """
    import subprocess
    import sys as _sys

    script = (
        "import sys, importlib, pkgutil\n"
        "import career_agent.domain as domain_pkg\n"
        "for _finder, name, _ispkg in pkgutil.walk_packages(\n"
        "    domain_pkg.__path__, prefix='career_agent.domain.'\n"
        "):\n"
        "    importlib.import_module(name)\n"
        "forbidden = {\n"
        "    'httpx', 'playwright', 'anthropic', 'sqlite3', 'langgraph', 'openpyxl'\n"
        "}\n"
        "loaded = {m for m in sys.modules if m.split('.')[0] in forbidden}\n"
        "print(','.join(sorted(loaded)))\n"
    )
    import os

    src_dir = str(Path(domain_pkg.__file__).parent.parent.parent)
    env = {**os.environ, "PYTHONPATH": src_dir}
    result = subprocess.run(
        [_sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    forbidden_loaded = {m for m in result.stdout.strip().split(",") if m}
    assert not forbidden_loaded, (
        f"importing career_agent.domain pulled in I/O libraries: {forbidden_loaded}"
    )
