"""Agents: the central Planner plus specialized capability agents.

- ``planner``  — the brain: decides what to do next, routes, prioritizes, retries.
- ``discovery`` — finds real openings from ATS APIs, YC/HN, career pages, search.
- ``resume``   — truthfully tailors resumes grounded in the master profile.
- ``apply``    — submits applications via the tiered, supervised applicator.
- ``learning`` — records outcomes and feeds them back into the system.

Implementations arrive in their respective roadmap phases.
"""
