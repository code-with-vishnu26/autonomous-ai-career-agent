# Architecture Decision Records (ADRs)

This directory records the significant architectural decisions made on this
project, and the context and consequences behind them. ADRs are immutable once
accepted: if a decision changes, we add a new ADR that supersedes the old one
rather than editing history.

## Format

Each ADR is a numbered Markdown file: `NNNN-short-title.md`, using the template
below.

```markdown
# ADR-NNNN: Title

- **Status:** Proposed | Accepted | Superseded by ADR-XXXX
- **Date:** YYYY-MM-DD

## Context
What is the situation and the forces at play?

## Decision
What we decided to do.

## Consequences
The results — positive, negative, and neutral — of the decision.

## Alternatives considered
What else we weighed and why we didn't choose it.
```

## Index

| ADR | Title | Status |
|-----|-------|--------|
| [0001](0001-agent-oriented-architecture.md) | Agent-oriented architecture (not a fixed pipeline) | Accepted |
