# Contributing

Thanks for your interest in the Autonomous AI Career Agent. This is a single-user,
self-hosted project, but it is open source and contributions are welcome.

## Ground rules (project working principles)

These apply to everyone, including maintainers:

1. **Build one phase at a time.** Follow [`ROADMAP.md`](ROADMAP.md). Don't land a
   later phase before its predecessors. Commit at phase boundaries.
2. **No silent re-architecture.** Don't rewrite the project structure or a major
   interface without discussion first. Open an issue.
3. **Document significant decisions as ADRs.** Any choice that shapes the
   architecture goes in [`docs/adr/`](docs/adr/) (see the format there).
4. **Explain fit before features.** Before implementing a new feature, briefly
   explain how it fits the existing architecture (plugin registry + event bus —
   new capabilities should plug in, not rewire the core).
5. **Truthfulness is non-negotiable.** Nothing may generate applicant-facing
   content that isn't grounded in the user's master profile. Never weaken the
   fabrication-detection gate.

## Production quality bar

Every change is expected to maintain production quality:

- **Type hints** everywhere; **Pydantic** models where validation earns its place.
- **Docstrings** on public modules, classes, and functions.
- **Tests** alongside the code (`tests/` mirrors `src/`).
- **Docs** updated in the same change as the code they describe.
- **Prompts** are versioned in git and covered by **promptfoo** regression tests;
  don't change a prompt without updating its evals.

## Development setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install   # once tooling lands
```

## Workflow

1. Open an issue describing the change and, for anything architectural, the ADR
   you intend to add.
2. Branch from the default branch.
3. Keep changes scoped to a single phase/concern.
4. Run the test suite and linters/formatters locally before pushing.
5. Open a pull request that references the issue and the relevant roadmap phase.

## Code style

- Formatting: **Black**; imports: **isort**; linting: **Ruff**; types: **mypy**.
- Prefer small, composable modules. Capabilities belong in `plugins/`, not in
  core orchestration.

## Commit messages

Write clear, descriptive commit messages. Conventional-commit style is
encouraged (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).
