"""Phase 47 (ADR-0065): enforces integrations/browser/'s zero-domain-
knowledge contract, the same enforceable-allowlist pattern
``tests/domain/test_purity.py`` uses for ``domain/``'s zero-I/O contract.

The whole point of this being a "foundation" layer (per the brief: "This
layer does NOT yet apply for jobs. It only manages browsers and
sessions."): nothing under ``career_agent.integrations.browser`` may
import ``career_agent.domain``, ``career_agent.agents``, or
``career_agent.storage`` at the top level -- it cannot know what a job
opportunity, a résumé, or an application is. This parses every module and
asserts every top-level import comes from an allowlist, instead of merely
asserting it in a docstring.
"""

from __future__ import annotations

import ast
from pathlib import Path

import career_agent.integrations.browser as browser_pkg

ALLOWED_TOP_LEVEL_IMPORTS = {
    # standard library
    "__future__",
    "asyncio",
    "pathlib",
    "typing",
    # the reason this package exists: real Chromium automation
    "playwright",
    # this project's own existing session-persistence primitive (ADR-0020)
    # -- reused, not duplicated -- and browser itself, for intra-package imports
    "career_agent",
}


def _browser_module_paths() -> list[Path]:
    package_dir = Path(browser_pkg.__file__).parent
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


def test_every_top_level_import_is_allowlisted() -> None:
    for path in _browser_module_paths():
        imports = _top_level_imports(path.read_text(encoding="utf-8"))
        disallowed = imports - ALLOWED_TOP_LEVEL_IMPORTS
        assert not disallowed, f"{path}: disallowed top-level imports {disallowed}"


def test_career_agent_submodule_imports_stay_within_integrations() -> None:
    """The one thing the coarse top-level check above can't see: a
    ``from career_agent.X import Y`` where X isn't ``integrations`` would
    still pass the top-level-only check (it starts with "career_agent").
    This walks every ``ImportFrom`` node directly and asserts the full
    dotted module path, when it starts with ``career_agent.``, stays
    within ``career_agent.integrations`` -- never
    ``career_agent.domain``/``.agents``/``.storage``/``.plugins``/``.llm``.
    """
    for path in _browser_module_paths():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.level == 0
                and node.module.startswith("career_agent.")
            ):
                assert node.module.startswith("career_agent.integrations"), (
                    f"{path}: {node.module!r} reaches outside "
                    f"career_agent.integrations -- the browser foundation "
                    f"layer must have zero knowledge of jobs/résumés/"
                    f"applications (ADR-0065)"
                )
