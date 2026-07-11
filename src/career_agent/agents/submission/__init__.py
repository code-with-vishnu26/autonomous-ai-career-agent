"""Submission Engine (Phase 53, ADR-0071).

The only package in this codebase allowed to click a real Submit button --
and only after every precondition in ``domain/execution.py``'s fail-closed
boundary holds, plus one final, explicit, un-bypassable human confirmation.
Reuses :class:`~career_agent.agents.apply.browser_applicator.BrowserApplicator`
(Tier 2, ADR-0020/0028/0032) unmodified for the actual browser-driving --
this package adds the safety gate in front of it, not a second
implementation of what it already does.
"""
