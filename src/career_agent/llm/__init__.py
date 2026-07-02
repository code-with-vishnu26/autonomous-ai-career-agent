"""LLM access: a single Claude client with a Haiku -> Sonnet -> Opus cost cascade.

Cheap models handle routine work; the system escalates to more capable (more
expensive) models only when a task needs it. Prompts are versioned in git and
guarded by promptfoo regression tests.

``claim_verifier.py`` and ``prompts.py`` (Phase 5, ADR-0016) are the first
concrete pieces built here -- narrowly, for the truthfulness gate's
``ClaimVerifier`` port specifically, and permanently exempt from the cost
cascade (a false-approve on a fabrication check is not a cost to optimize
away). The general cascade client this package's docstring describes is still
future work; ``AnthropicClaimVerifier`` does not depend on it.
"""
