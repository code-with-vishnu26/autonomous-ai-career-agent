# ADR-0037: SQLite persistence, the real discover command, the first MasterProfile writer, and the Excel tracker

- **Status:** Accepted
- **Date:** 2026-07-04
- **References:** [ADR-0014](0014-cross-source-opportunity-identity.md)
  (the two-key dedup the SQLite repository reproduces exactly),
  [ADR-0026](0026-real-apply-command-and-promptfoo-enforcement.md) (the
  opportunity-file handoff `discover` now produces for real),
  [ADR-0032](0032-question-answerer-wiring.md) (which named the missing
  MasterProfile writer this ADR builds), [ADR-0017](0017-master-profile-loader.md)

## Decision

**`SqliteOpportunityRepository`** (`storage/sqlite.py`): the drop-in
persistent implementation of the exact `add`/`get` contract, with
byte-for-byte the in-memory dedup semantics — proven by a fidelity suite
that mirrors the in-memory scenarios (same public-surface guard included)
plus the one thing memory can't prove: full-model round-trip and dedup
state surviving a real close/reopen. Plain stdlib sqlite3, synchronous
under the async methods — single-user local scale, documented.

**`SqliteApplicationStore`**: append-only audit trail (one row per
tailoring/submission attempt, recorded at the composition root after
`apply` runs; `record` never overwrites — verified). Outcomes (Phase 15)
append to their own table; history is never mutated.
`ResumeTailoringResult` gained `ats_report` (additive, default `None`) so
the recorded row carries the real final ATS score.

**`career-agent discover`**: runs every source whose config exists
(`build_discovery_sources` wires Tier A keys/flags from Settings), dedups
through the repository, and writes each genuinely-new opportunity as the
exact JSON handoff file `apply --opportunity-file` already consumes —
ADR-0026's format produced for real for the first time, with zero change
to `apply`. Per-source failure isolation: a broken API is reported and
skipped, never silent, never fatal to the run.

**The first `MasterProfile` writer** (`save_legal_status` +
`career-agent capture-legal-status`): explicit-confirmation capture of
`LegalStatusSection` only. Accepts exactly `yes`/`no`/`skip`; anything
else — including empty input — leaves the fact **exactly as it was**
(injection-verified: making garbage default to "no" was caught).
`skip`/garbage can never become an answer in either polarity; an explicit
`no` is a genuine captured `False`, distinct from `None`'s "never asked."
The writer touches only the `legal_status` key — unmodeled JSON Resume
sections survive byte-identical (tested against an `awards` section).
Version-bump semantics: the content hash naturally changes on next load;
nothing rewrites the frozen snapshots on existing Applications
(ADR-0027/0032 discipline preserved). The loader now round-trips
`legal_status` (absent key → all-`None`, backward compatible).

**Excel tracker** (`storage/excel.py`, `career-agent export`): the
founding-brief requirement — one formatted, filterable openpyxl workbook
(bold frozen header, auto-filter) of every recorded application: company,
title, source, ATS score, truthfulness verdict, status, tier, profile and
prompt versions, artifact file paths, latest outcome.

## Trade-offs

- **(+)** Discovery→persistence→apply→audit→export is now one real,
  runnable loop with no interface renegotiated anywhere.
- **(−)** `apply` records the attempt row itself at the composition root
  rather than via events — direct and simple; if a second writer appears,
  revisit event-driven recording (events still never gate).
- **(−)** ATS-refused runs are not recorded as rows this slice (the typed
  error aborts before recording) — named future wiring, not silent.

## Future revisit criteria

- ATS/truthfulness refusals should appear in the tracker → record from
  the exception paths too.
- Multi-process access ever becomes real → revisit sqlite locking mode.
