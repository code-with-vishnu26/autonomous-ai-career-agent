"""Phase 49 (ADR-0067): the search-planning modules are provably pure --
no I/O, no network, no adapter/browser call, no ``async def`` anywhere.
Same enforceable-not-asserted discipline as
``tests/domain/test_purity.py``/``tests/integrations/test_browser_purity.py``.
"""

from __future__ import annotations

import ast
from pathlib import Path

_PLANNER_DIR = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "career_agent"
    / "agents"
    / "planner"
)
_NEW_MODULES = (
    "execution_plan.py",
    "provider_selector.py",
    "budget.py",
    "planning_rules.py",
    "planner.py",
)

_FORBIDDEN_TOP_LEVEL_IMPORTS = {
    "httpx",
    "requests",
    "playwright",
    "asyncio",
    "socket",
}


def _top_level_imports(source: str) -> set[str]:
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module.split(".")[0])
    return modules


def test_no_forbidden_io_imports_in_any_planning_module() -> None:
    for name in _NEW_MODULES:
        source = (_PLANNER_DIR / name).read_text(encoding="utf-8")
        found = _top_level_imports(source) & _FORBIDDEN_TOP_LEVEL_IMPORTS
        assert not found, f"{name}: forbidden I/O-shaped import(s) {found}"


def test_no_async_functions_in_any_planning_module() -> None:
    """No I/O-shaped function signature anywhere -- planning is
    synchronous, deterministic computation only, this phase."""
    for name in _NEW_MODULES:
        source = (_PLANNER_DIR / name).read_text(encoding="utf-8")
        tree = ast.parse(source)
        async_defs = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef)
        ]
        assert not async_defs, f"{name}: unexpected async def(s) {async_defs}"
