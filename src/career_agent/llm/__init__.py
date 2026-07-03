"""LLM access: a single Claude client with a Haiku -> Sonnet -> Opus cost cascade.

Cheap models handle routine work; the system escalates to more capable (more
expensive) models only when a task needs it. Prompts are versioned in git and
guarded by promptfoo regression tests.

``claim_verifier.py`` (Phase 5, ADR-0016) is narrowly scoped for the
truthfulness gate's ``ClaimVerifier`` port, and permanently exempt from the
cost cascade (a false-approve on a fabrication check is not a cost to
optimize away).

``content_drafter.py`` (Phase 8a, ADR-0022) is narrowly scoped for
``ResumeGenerator``'s ``ContentDrafter`` port -- but, unlike the verifier,
**not** permanently cascade-exempt: a false-approve on tailoring is
recoverable via the independent gate downstream, so the asymmetry that
earned ``ClaimVerifier`` its exemption doesn't transfer here. Cascade
tiering for this port is real, undecided future work.

``prompts.py`` holds both ports' git-versioned prompt text. The general
cascade client this package's docstring describes is still future work;
neither concrete class here depends on it.

``promptfoo_gate.py`` (Phase 8e, ADR-0026) is not a port implementation --
it is the mechanism that positively verifies, against an actual results
artifact on disk, that the promptfoo suite has passed for the current
truthfulness-gate prompt version before ``cli.py`` constructs a real
``AnthropicClaimVerifier``. This is what makes ADR-0016's promptfoo
requirement a structural check rather than a policy a future run could
silently skip.
"""
