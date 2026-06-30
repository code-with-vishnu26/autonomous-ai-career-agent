"""Autonomous AI Career Agent.

A single-user, self-hosted automation that discovers, decides on, applies to, and
learns from job opportunities using the user's own accounts and data.

The package is organized around an agent-oriented architecture (see ADR-0001):
a central Planner Agent coordinates specialized agents (Discovery, Resume, Apply,
Learning) that communicate through a plugin registry and event bus.
"""

__version__ = "0.1.0"
