"""Core building blocks: event bus, plugin registry, interfaces, and config.

This package holds the orchestration *machinery* every agent depends on: the
event catalog (``events.py``), the typed contracts agents and plugins
implement against (``interfaces.py``), and (later) the plugin registry
(Phase 3) and settings. Domain *data* -- Opportunity, Application,
MasterProfile, and friends -- lives in ``career_agent.domain`` instead, kept
free of any dependency on this package so it stays trivially testable and
never churns when orchestration mechanics change.
"""
