"""LLM access: a single Claude client with a Haiku -> Sonnet -> Opus cost cascade.

Cheap models handle routine work; the system escalates to more capable (more
expensive) models only when a task needs it. Prompts are versioned in git and
guarded by promptfoo regression tests.
"""
