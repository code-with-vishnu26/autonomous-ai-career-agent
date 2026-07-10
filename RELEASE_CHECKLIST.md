# Release Checklist — Autonomous AI Career Agent

This checklist is the gate for cutting a release. It mirrors the Phase 34 audit
and must be re-run from a clean tree. Record exact results, not summaries.

## 0. Position

- [ ] Release position is **`PREPARE_ONLY`** and docs do not claim autonomous
      external submission (ADR-0056).

## 1. Repository reality

- [ ] `git status` clean; on the intended branch.
- [ ] `origin/main` and local HEAD reconciled.
- [ ] ADR index is continuous; ROADMAP reflects the last merged phase.

## 2. Baseline (fresh, exact counts)

- [ ] `pytest` — record `N passed / N skipped / N failed`.
- [ ] `ruff check .` — `All checks passed!`
- [ ] `lint-imports` — `Contracts: 4 kept, 0 broken.`

## 3. Safety re-proof

- [ ] Truthfulness gate rejects unsupported skill / seniority / metric / action.
- [ ] JD is never passed to the gate; every revision is re-gated.
- [ ] Rejected drafts are never ATS-scored.
- [ ] Verifier exceptions and malformed provider output fail closed.
- [ ] Promptfoo gate blocks a missing / malformed / wrong-provider / wrong-version
      artifact.

## 4. External-action reachability

- [ ] No `Applicator` is constructed by any CLI path.
- [ ] `apply` / `auto` end at the execution boundary with
      `executor_available=False`, printing "nothing was actually sent."
- [ ] Classification: **UNREACHABLE**.

## 5. Idempotency / journal

- [ ] Prior non-rejected attempt is detected and skipped.
- [ ] Restart does not duplicate a prepared application.
- [ ] Journal is append-only; run_ids stable per run, distinct across runs.

## 6. Privacy / secrets

- [ ] No API key / token committed (`git grep` for `sk-` / `gsk_` / `AKIA`).
- [ ] `.env`, `*.db`, `*.sqlite`, `*.xlsx`, `promptfoo/results/` are git-ignored.
- [ ] No private candidate artifact tracked or packaged.

## 7. Promptfoo

- [ ] If a valid local `promptfoo/results/` artifact exists, run
      `career-agent verify-promptfoo --provider <p>` and record PASS.
- [ ] If absent: live verifier validation is **BLOCKED_BY_CONFIGURATION** — do
      not claim it happened.

## 8. Packaging

- [ ] `python -m build` produces wheel + sdist.
- [ ] `python scripts/verify_release_artifacts.py` passes (wheel contains no
      secrets/`.env`/results/DBs/exports/tests; sdist contains no
      secrets/`.env`/results/DBs/exports — `tests/` is expected there).
- [ ] `python scripts/smoke_test_wheel.py` passes (clean-venv install,
      `career-agent --help`, `setup` smoke).

## 9. Cross-platform

- [ ] Linux: full suite green (CI, every push/PR, ADR-0057).
- [ ] Windows: full suite + packaging + smoke green (CI, every push/PR,
      ADR-0057) — no longer inferred from static UTF-8 reasoning alone.
- [ ] macOS: **untested** (deliberate, cost-driven gap; ADR-0056/0057).

## 10. CI

- [ ] Inspect the **actual** latest check-run conclusions for the commit being
      released (`.github/workflows/ci.yml`, ADR-0057) — do not infer from the
      YAML alone or assume a run passed without checking it.
- [ ] Both matrix legs (`ubuntu-latest`, `windows-latest`) are green.

## 11. Sign-off

- [ ] Version metadata set intentionally (see `docs/release/`).
- [ ] Draft PR opened; **not** merged; **not** tagged; **not** published without
      authorization.
- [ ] Explicit **GO / CONDITIONAL_GO / NO_GO** recorded with reasoning.
