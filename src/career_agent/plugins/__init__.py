"""Pluggable capabilities that self-register against core extension points.

Subpackages:

- ``ats``      — ATS adapters (Greenhouse, Lever, Ashby, ...).
- ``sources``  — opportunity sources (YC, Hacker News, career pages, ...).
- ``search``   — web-search providers (Exa, Google CSE, ...).

Adding a capability here should require only a plugin registration plus event
wiring — never a core rewrite (see ADR-0001).
"""
