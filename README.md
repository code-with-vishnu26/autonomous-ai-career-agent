# Autonomous AI Career Agent

> A single-user, self-hosted automation that discovers, decides on, applies to,
> and learns from job opportunities on your behalf — using **your** accounts and
> **your** data, running on **your** machine.

This is **not** a mass job-application bot and **not** a multi-tenant SaaS. It is
a personal agent you own end-to-end. Its guiding principle is **quality over
volume**: fewer, sharper, *truthful* applications.

---

## What it does

The agent delivers four product capabilities — **Discover → Decide → Apply →
Learn** — coordinated by a central **Planner Agent** that decides what to do
next, dispatches work to specialized agents, and handles failures, retries, and
prioritization.

| Capability | Agent | Responsibility |
|------------|-------|----------------|
| **Discover** | Discovery Agent | Find real openings from open ATS APIs, YC, Hacker News, company career pages, and a provider-abstracted web-search layer. |
| **Decide** | Planner Agent | Score and prioritize opportunities; decide what's worth pursuing. |
| **Apply** | Apply Agent | Tailor a truthful résumé and submit through a tiered, human-in-the-loop applicator. |
| **Learn** | Learning Agent | Track outcomes and improve scoring, targeting, and résumé tailoring over time. |

## Core commitments

- **Truthfulness is non-negotiable.** Résumé tailoring may only use facts present
  in your structured master profile (JSON Resume schema). A **fabrication-detection
  gate** blocks any application whose content isn't grounded in that profile.
- **Open-ended discovery.** Public ATS JSON APIs (Greenhouse / Lever / Ashby)
  first, then YC `hiring.json` + Hacker News "Who's Hiring," then company career
  pages (via a Career Page Finder + ATS Detector), then a provider-abstracted web
  search (Exa + Google CSE with failover). Job boards only within their ToS.
- **Supervised, human-in-the-loop applying.** A tiered applicator (direct ATS API
  → driven browser → email-to-apply via Gmail) that *pauses for you* to clear any
  CAPTCHA or verification. Throttled, reuses a session from a manual login, and
  never automates Google OAuth itself.
- **Agent-oriented, not a fixed pipeline.** Capabilities register through a
  **plugin registry + event bus**, so new ATS adapters, opportunity sources, and
  search providers plug in without core rewrites.

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the full design and
[`docs/adr/`](docs/adr/) for the decisions behind it.

## Tech stack

- **Language:** Python 3.11+
- **LLM:** Anthropic Claude with a **Haiku → Sonnet → Opus** cost cascade
- **Orchestration:** LangGraph
- **Storage:** SQLite + openpyxl (spreadsheet exports)
- **Browser automation:** Playwright + Browser-Use
- **Email:** Gmail connector
- **Prompt engineering:** git-based prompt versioning + promptfoo regression tests

## Status

🚧 **Early development.** The project is being built in discrete phases — see
[`ROADMAP.md`](ROADMAP.md). This commit establishes the project scaffolding
(Phase 1).

## Quick start

> Not yet runnable — scaffolding only. Setup instructions will land as the
> phases below are implemented.

```bash
git clone <this-repo>
cd autonomous-ai-career-agent
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # then fill in your keys
```

## License

[MIT](LICENSE) — built to be self-hosted and owned by the person running it.
