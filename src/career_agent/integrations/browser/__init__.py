"""Browser Automation Foundation (Phase 47, ADR-0065).

Low-level browser/session/tab lifecycle primitives -- ``BrowserManager``
(launch/close Chromium), ``SessionManager`` (persist/reuse a login session;
wait for, never automate, a human login), ``TabManager`` (multi-tab
tracking within one context). Nothing in this subpackage knows what a job
opportunity, a résumé, or an application form is: it imports nothing from
``career_agent.domain``/``career_agent.agents``, only Playwright's own
types and this project's existing
:class:`~career_agent.integrations.browser_session.EncryptedSessionStore`.

This layer does not open, read, or fill a job application. That remains
:class:`~career_agent.agents.apply.browser_applicator.BrowserApplicator`'s
job (unwired from the CLI, ADR-0026/0050) -- a *future* phase's job to
build the next layer that consumes this one for that purpose, not this
phase's.
"""
