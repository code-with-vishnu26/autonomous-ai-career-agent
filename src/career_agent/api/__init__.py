"""Web Dashboard read API (Phase 54, ADR-0072).

A thin FastAPI layer over the existing storage layer -- no business logic
lives here. Every route wraps a store class (``SqliteApplicationSessionStore``,
``SqliteReviewSessionStore``, ``SqliteSubmissionResultStore``,
``SqliteResumeVariantStore``) that the CLI already writes to via
``career-agent prepare``/``review``/``submit``; this package only reads what
the CLI produced and never re-implements or bypasses any of it.

Scope of this phase, deliberately: **read-only**. No route here can trigger a
discovery search, a tailoring run, a review approval, or a submission --
those remain exclusively reachable through the CLI (``career-agent
discover``/``prepare``/``review``/``submit``), preserving every safety gate
Phases 51-53 built (most importantly the human-in-the-loop boundary in
``domain/execution.py``). Write-capable dashboard actions are an explicit,
separately-reviewed follow-up phase, not part of this one.
"""

from __future__ import annotations
