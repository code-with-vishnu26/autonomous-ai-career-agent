"""Example plugins that demonstrate the registration + discovery machinery.

These are illustrative, not production capabilities -- real search providers,
ATS adapters, and sources arrive in Phase 4+. Nothing here registers itself
until a caller explicitly runs
:func:`career_agent.core.registry.discover` on this package with a target
registry, so importing the package is free of side effects.
"""
