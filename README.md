# Autonomous AI Career Agent

> A single-user, self-hosted assistant that discovers job openings, ranks them,
> ingests your CV as evidence, and **prepares** truthful, ATS-tuned application
> materials for your review — using **your** accounts, **your** data, and
> **your** machine.

This is **not** a mass job-application bot and **not** a multi-tenant SaaS. It is
a personal agent you own end-to-end. Its guiding principle is **quality over
volume**: fewer, sharper, *truthful* applications.

**Release position (v1.0): `PREPARE_ONLY`.** The agent prepares everything up to
a human confirmation and then **stops** — it does **not** submit applications to
any external system. See [Scope & limitations](#scope--limitations) and
[ADR-0056](docs/adr/0056-v1-prepare-only-release-scope.md).

---

## What it does

| Capability | Responsibility |
|------------|----------------|
| **Discover** | Find real openings from open ATS APIs (Greenhouse / Lever / Ashby), YC `hiring.json`, Hacker News "Who's Hiring," company career pages, and a provider-abstracted web-search layer. Dedup and persist them. |
| **Decide** | Score and rank opportunities deterministically (Pareto + sensitivity analysis, hard exclusions); decide what's worth pursuing. |
| **Ingest** | Parse a CV (`.docx` / `.txt` / `.md`) into **unverified**, source-bound fact proposals. You confirm each one; only confirmed facts are promoted into your profile. |
| **Prepare** | Tailor a résumé from your profile, enforce a fabrication-detection **truthfulness gate**, run an **ATS score gate** with a bounded revision loop, render artifacts, and ask for a real human confirmation — then stop. |
| **Learn** | Track outcomes and funnel counts to inform future targeting. |

## Core commitments

- **Truthfulness is non-negotiable.** Résumé tailoring may only use facts present
  in your structured master profile (JSON Resume schema). A **fabrication-detection
  gate** blocks any application whose content isn't grounded in that profile — the
  job description is never treated as evidence. Unsupported skills, seniority,
  metrics, and action claims are rejected.
- **CV facts are untrusted until you confirm them.** Imported CV content becomes
  *proposals*, never silent profile edits. Promotion is fail-closed and never
  overwrites a different verified value (see
  [ADR-0052](docs/adr/0052-evidence-grounded-cv-ingestion.md)).
- **Prepare-only, by construction.** No automated executor is wired. Every
  `apply`/`auto` run ends at a confirmation boundary that refuses execution and
  reports "nothing was actually sent" (see
  [ADR-0050](docs/adr/0050-execution-safety-boundary.md) and
  [ADR-0054](docs/adr/0054-production-readiness-release-gate.md)).
- **Idempotent and recoverable.** A prior non-rejected attempt for the same
  opportunity is detected and skipped; runs are recorded in an append-only
  execution journal (ADR-0048 / ADR-0049).
- **Agent-oriented, not a fixed pipeline.** Capabilities register through a
  plugin registry + event bus, so new sources and adapters plug in without core
  rewrites.

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the full design and
[`docs/adr/`](docs/adr/) for the decisions behind it.

## Scope & limitations

| Area | v1.0 status |
|------|-------------|
| Discover, rank, ingest, confirm, promote, tailor, gate, ATS, render, journal, report, export | **SUPPORTED** |
| PDF CV import / OCR | **NOT_SUPPORTED** (`.docx` / `.txt` / `.md` only) |
| Browser submission / email-to-apply / autonomous external submission | **NOT_SUPPORTED** — code exists but is **unwired and unreachable** from the CLI |
| Live LLM output *quality* | Validated by a real controlled live-Groq smoke run (Phase 36) — CI itself never has an API key, so it can make **no** real LLM call |
| CI | Runs on every push/PR to `main`: lint, architecture contracts, full test suite, packaging, clean-install, and an offline CLI smoke — on **Linux and Windows** |
| macOS | **Untested** — a deliberate, documented gap, not silently dropped |

The full capability matrix and known limitations live in
[`docs/release/v1.0.0-notes.md`](docs/release/v1.0.0-notes.md).

## Tech stack

- **Language:** Python 3.11+
- **LLM providers:** Groq free tier (**preferred**: `openai/gpt-oss-120b` verifier,
  `llama-3.3-70b-versatile` drafter/matcher) with Anthropic Claude as a paid
  fallback (`claude-opus-4-8` / `claude-haiku-4-5-20251001`). Selection is
  fail-closed when no key is configured.
- **Storage:** SQLite + openpyxl (spreadsheet exports)
- **Prompt validation:** git-based prompt versioning + a fail-closed promptfoo
  regression gate keyed by prompt version and provider

## Quick start

**Only editable install from a cloned source checkout is currently verified.**
There is no PyPI package and no published GitHub Release asset yet — do not
`pip install` this from anywhere except a local clone.

Linux / macOS (bash/zsh):

```bash
git clone https://github.com/code-with-vishnu26/autonomous-ai-career-agent
cd autonomous-ai-career-agent
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # then add GROQ_API_KEY (preferred) or ANTHROPIC_API_KEY

career-agent setup     # scaffolds a starter profile + prints an offline readiness report
```

Windows (PowerShell):

```powershell
git clone https://github.com/code-with-vishnu26/autonomous-ai-career-agent
cd autonomous-ai-career-agent
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env   # then add GROQ_API_KEY (preferred) or ANTHROPIC_API_KEY

career-agent setup     # scaffolds a starter profile + prints an offline readiness report
```

Then edit `profile.json` with your real, truthful details and re-run
`career-agent setup`. The profile follows the
[JSON Resume](https://jsonresume.org/) schema — dates use its camelCase
convention (`startDate` / `endDate`, not `start_date`); a scaffolded work
entry looks like:

```json
{
  "id": "w1",
  "name": "Acme Corp",
  "position": "Software Engineer",
  "startDate": "2023-01-01",
  "endDate": "2024-06-01",
  "highlights": ["Built and shipped a real feature"]
}
```

For a real Groq/Anthropic key to pass truthfulness validation, you also need
a local Promptfoo evidence run — see
[`promptfoo/README.md`](promptfoo/README.md) for the exact command;
`career-agent verify-promptfoo` checks the result it produces before `apply`
will use a real provider.

Core commands:

```
career-agent setup | import-cv | promote-cv | discover | apply | auto
career-agent outcome | report | export | verify-promptfoo | diagnose-promptfoo-drift
```

`career-agent --help` lists them all. `apply` and `auto` prepare materials and
stop at confirmation; neither submits.

## Privacy

Your profile, CV proposals, SQLite database, spreadsheet exports, rendered
résumés, and any promptfoo result artifacts stay on your machine. They are
git-ignored and never committed or packaged (see [`SECURITY.md`](SECURITY.md)).

## Status

**v1.0.0** — a supervised, prepare-only release, promoted from `1.0.0rc1`
after a real controlled live-Groq validation and green CI on Linux and
Windows (Phase 37). See [`ROADMAP.md`](ROADMAP.md) and
[`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md).

## License

[MIT](LICENSE) — built to be self-hosted and owned by the person running it.
