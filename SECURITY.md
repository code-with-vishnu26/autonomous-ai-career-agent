# Security Policy

## Scope

The Autonomous AI Career Agent is a **single-user, self-hosted** tool. It runs
on the operator's own machine, with the operator's own accounts and data. There
is no hosted service, no multi-tenancy, and — in v1.0 — no autonomous external
action. This document records the security properties the project relies on and
how to report a problem.

## Reporting a vulnerability

Open a private security advisory on the repository, or contact the maintainer
directly. Please do **not** file a public issue for an undisclosed
vulnerability. Include a description, affected version/commit, and a minimal
reproduction if possible.

## Trust boundaries

| Boundary | Trusted? | Enforcement |
|----------|----------|-------------|
| Structured master profile (`profile.json`) | **Trusted** — the sole source of résumé evidence | Truthfulness gate reads evidence only from the profile |
| Imported CV content | **Untrusted** until explicitly confirmed | Ingestion produces UNVERIFIED proposals; promotion is fail-closed (ADR-0052) |
| Job description text | **Untrusted** | The JD reaches the drafter but is **never** passed to the truthfulness gate (`verify(draft, profile)` has no JD parameter) |
| LLM provider responses | **Untrusted** | Malformed / reasoning-preamble / truncated output is a parse error → explicit block, never a silent pass |
| Promptfoo result artifacts | **Untrusted** | Fail-closed gate: requires `errors == 0`, `successes == expected`, matching prompt version + provider id |

## Key security properties (v1.0)

- **No unsupported material claim can be accepted.** Unsupported skills,
  seniority, metrics, and inferred actions are rejected; deterministic Layer-1
  checks catch most without a model call (ADR-0044).
- **Prompt injection from a job description cannot promote a fabricated claim.**
  The JD is untrusted data, not evidence; every drafter output is re-gated;
  unsupported skills fail a structural membership test.
- **External submission is unreachable.** No executor is wired; the execution
  boundary is hardcoded fail-closed (`executor_available=False`) and always
  refuses (ADR-0050 / ADR-0054). Browser/email submission code exists but is not
  constructed by any CLI path.
- **Provider misconfiguration fails closed.** A missing key raises rather than
  silently proceeding; the truthfulness gate is Promptfoo-validated before the
  live verifier is constructed.
- **Tests cannot make real LLM calls.** An autouse fixture blocks
  `api.groq.com` / `api.anthropic.com`; only `httpx.MockTransport` doubles are
  allowed.

## Secrets and private data

- API keys are read from the environment / `.env` (git-ignored; only
  `.env.example` is committed). No key is ever committed or logged.
- Private candidate data — `profile.json`, CV proposals, SQLite databases
  (`*.db` / `*.sqlite`), spreadsheet exports (`*.xlsx`), rendered résumés, and
  `promptfoo/results/` — is git-ignored and excluded from the built wheel and
  sdist. The packaging audit in `RELEASE_CHECKLIST.md` verifies this every
  release.

## Supported versions

Security fixes target the latest release/branch. Pre-1.0 tags are development
snapshots and are not separately maintained.
