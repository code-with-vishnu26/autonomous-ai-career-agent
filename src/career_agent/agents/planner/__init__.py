"""Planner Agent — the brain (Phase 2+).

Decides what to do next given system state, dispatches work to specialized
agents, owns prioritization, retry/backoff, human-in-the-loop pauses, and the
Claude cost-cascade budget. Built on LangGraph for an inspectable, resumable
decision loop.
"""
