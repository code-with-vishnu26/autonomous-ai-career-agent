"""Website Adapter Framework (Phase 48, ADR-0066).

A common interface (:mod:`base`) over per-platform adapters
(Greenhouse/Lever/Ashby/Workday/RemoteOK/Remotive/Arbeitnow/TheMuse), a
deterministic URL-based lookup (:mod:`registry`), and browser hooks that
reuse Phase 47's ``BrowserManager``/``SessionManager``/``TabManager``.

No adapter knows what a résumé, an application, or the truthfulness gate
is -- discovery (``search()``) delegates to this project's existing,
real, tested :class:`~career_agent.core.interfaces.OpportunitySource`
implementations where one exists; only the browser-facing half
(opening a URL, generic page metadata, login detection) is new. No
adapter fills a form or submits anything -- ``prepare_application()``
always raises :class:`~career_agent.integrations.adapters.base.
FeatureUnavailableError`, deliberately, this phase.
"""
