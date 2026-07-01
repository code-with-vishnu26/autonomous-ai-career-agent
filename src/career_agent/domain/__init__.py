"""Domain models: pure data and business rules, zero I/O.

This package holds nothing but Pydantic models and the pure business
constants they need (e.g. funnel ordering). It must never import a
networking client, a database driver, a browser-automation library, or an
LLM SDK -- and importing anything in this package must never pull one in
transitively either. That constraint is the enforceable test in
``tests/domain/test_purity.py``: it is not just a principle, it is asserted.

Keeping domain dependency-free is what lets every other layer (core, agents,
plugins, storage) depend on it freely without risking a circular import, and
lets these models be tested in milliseconds with no fixtures.
"""
