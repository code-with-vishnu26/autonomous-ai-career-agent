# ADR-0061: sdist packaging uses a positive top-level allowlist, not a blocklist alone (Phase 41)

- **Status:** Accepted
- **Date:** 2026-07-10
- **References:** ADR-0057 (CI/packaging hardening, introduced
  `scripts/verify_release_artifacts.py`), ADR-0060 (runtime-path
  portability policy)

## Context

Phase 41's installed-package/distribution audit built a fresh sdist and
inspected its actual contents (not merely re-ran the existing blocklist
check). It found a real leak: `.claude/` (this agent's own local session
state directory) and `.import_linter_cache/` appeared as top-level entries
in the built sdist.

Root cause: hatchling's default sdist packaging includes anything not
explicitly `.gitignore`d — **untracked-but-not-`.gitignore`d is not the
same as excluded.** Both directories were genuinely untracked by git (never
committed) but neither was covered by any pattern in `.gitignore`, so they
were swept in. Confirmed directly: adding both to `.gitignore` removed them
from a rebuilt sdist; a control test (a `*.db`-matching file, which *is*
`.gitignore`d) was already correctly excluded, proving hatchling's sdist
packaging does respect `.gitignore` — the gap was in `.gitignore`'s
coverage, not in hatchling's mechanism.

`scripts/verify_release_artifacts.py` (ADR-0057) did not catch this: its
checks are a **suffix/fragment blocklist** (`.db`, `.env`, `promptfoo/
results`, …), which can only flag patterns it already knows to look for. A
blocklist can never catch an *unanticipated directory* — by definition, it
wasn't anticipated.

## Decision

1. **`.gitignore` gains explicit entries** for `.claude/` and
   `.import_linter_cache/` — local tool/agent-session state, never
   intended to be tracked or shipped, following the same convention as the
   adjacent `.pytest_cache/`/`.mypy_cache/`/`.ruff_cache/` entries.
2. **`scripts/verify_release_artifacts.py` gains a positive top-level
   allowlist for the sdist** (`_SDIST_ALLOWED_TOP_LEVEL`): every top-level
   entry a legitimate sdist may contain, enumerated explicitly. Any entry
   not on the list fails the check closed. This is a **durable packaging
   policy**, not merely today's bugfix: a future genuinely-new top-level
   source file or directory requires a deliberate one-line addition to the
   allowlist, so the check can never again silently pass an unanticipated
   leak the way the blocklist-only check did. Verified both ways: a
   reintroduced junk directory now fails the check; the current legitimate
   sdist passes cleanly.
3. **`pyproject.toml`'s `classifiers` corrected**: `Development Status ::
   2 - Pre-Alpha` → `5 - Production/Stable`, matching the actual, tagged,
   CI-green `v1.0.0` release state (this classifier had never been updated
   across the entire v1.0.0 release-promotion arc).
4. **`requirements.txt`'s stale comment corrected**: "Haiku -> Sonnet ->
   Opus cost cascade" described a provider strategy abandoned phases ago;
   the actual policy (Groq preferred, Anthropic paid fallback) is now
   stated accurately, matching `README.md`/`.env.example` (already
   corrected in Phase 34/35).

## What this proves and what it does not

Proves: the sdist's *known-good* contents build cleanly and correctly
identify as `career-agent` v1.0.0, distinct from the repo name
(`autonomous-ai-career-agent`) and the import package name
(`career_agent`) — confirmed by building fresh wheel, sdist, and installing
each into independent clean environments, then running the CLI from a
directory outside the repository (source-tree independence, wheel and
sdist both).

Does not change: any safety semantics, Promptfoo gate behavior, dependency
versions, or the runtime path-resolution policy (ADR-0060) — this ADR is
packaging hygiene only.

## Consequences

- `.gitignore`: two new entries.
- `scripts/verify_release_artifacts.py`: `_SDIST_ALLOWED_TOP_LEVEL` +
  `_sdist_top_level_violations()`, wired into `main()` for the sdist target
  only (the wheel's existing test-path/secret checks are unchanged).
- `pyproject.toml`: one classifier corrected.
- `requirements.txt`: one stale comment corrected.
- New `tests/test_phase41_distribution_hardening.py` (5 tests): the
  allowlist rejects the exact leaked directory, accepts every currently
  legitimate entry, `.claude`/`.import_linter_cache` are proven git-ignored
  (via `git check-ignore`, not by reading `.gitignore` text), the
  classifier reflects the stable release state, and distribution/import/
  CLI/repo names are pinned as four distinct strings.
- No dependency version changed. No safety semantics changed. No new
  CI platform added (installed-package behavior was already exercised on
  both Ubuntu and Windows via the existing "Clean-venv install + CLI
  smoke" CI step — confirmed, not assumed, from that step's real green
  conclusion on both legs).

## Future revisit criteria

Revisit `_SDIST_ALLOWED_TOP_LEVEL` whenever a genuinely new top-level
source file or directory is intentionally added to the repository — the
check is designed to force that decision to be explicit, not to be
"fixed" by broadening it speculatively.
