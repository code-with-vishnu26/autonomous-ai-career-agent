"""Application Preparation Engine (Phase 51, ADR-0069).

Prepares a real, live application inside a browser -- fills known identity/
résumé fields, auto-answers what can be safely answered from a captured
profile fact, and manifests everything else for a human -- then stops.
Nothing in this package ever clicks a submit button; see
:mod:`career_agent.agents.application.engine` for the structural guarantee.
"""
