"""Offline research/validation infra for decision intelligence (ADR-0045/6/7).

Not part of the shipped ``career_agent`` package (mirrors ``promptfoo/``'s
precedent: a top-level directory adjacent to, not inside, the installed
package, for validation infrastructure that imports the production code
but is never imported by it). Nothing here makes a network call, calls an
LLM, or costs money.
"""
