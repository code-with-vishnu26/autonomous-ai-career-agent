# ADR-0083: Excel Export over the Web

- **Status:** Accepted
- **Date:** 2026-07-13
- **References:** [ADR-0037](0037-excel-application-tracker.md) (the
  original Excel application-tracker export this phase exposes over HTTP,
  unchanged on disk), [ADR-0071](0071-human-approved-submission-engine.md)
  (`export_submissions` and the `SubmissionResult` rows it serializes),
  [ADR-0072](0072-web-dashboard-read-api.md) (the read-only dashboard API
  boundary this stays inside), [ADR-0082](0082-per-user-master-profile-onboarding.md)
  (the immediately-prior "move the interface to the web" phase this
  continues)

## Context

The founding brief always included "store the details in a formatted,
filterable Excel sheet," and it has been real since Phase 13
(`storage/excel.py`, `career-agent export`). But it was **CLI-only**: a
dashboard user who never opens a terminal had no way to get the
spreadsheet, even though the dashboard already shows them every row it
would contain.

The originating request for the current program was explicit: a normal
user should never need a terminal, and "at last the details should store
in an Excel sheet." Excel export is the one genuinely-missing legitimate
piece of that flow.

**A repository-reality audit found:**

- `storage/excel.py` already produces exactly the rich workbook the
  request describes -- company, title/role, source/provider, ATS score,
  truthfulness verdict, status, dates, file paths, latest outcome -- via
  `export_applications` (old `apply` pipeline `Application` rows) and
  `export_submissions` (`SubmissionResult` rows). `openpyxl>=3.1` is
  already a dependency. Nothing about the *content* needed building.
- Both existing functions write only to a `Path` on disk. A web download
  needs the same bytes streamed from memory, without a temp file.
- The dashboard's own "applications" surface is `ApplicationSession`
  (what `prepare` writes and `/api/applications` returns), which is a
  *different* record type from the `apply` pipeline's `Application` --
  the two were never unified (ADR-0069/0070/0071 each note this). So a
  web "download my applications" needs an `ApplicationSession` export,
  which did not exist.
- Every dashboard data route is scoped to `current_user.id` and every
  `/api/*` route is GET-only by a structural test. A download endpoint is
  read-only but returns a binary attachment, not JSON.

## Decision

Expose the existing Excel export over HTTP, scoped per user, changing
nothing about the on-disk CLI output.

**`storage/excel.py`:**

- Extract a shared `_build_workbook(title, columns, rows)` (bold frozen
  header, auto-filter, uniform width) that both existing exports now call
  -- their output is byte-for-byte unchanged (proven by the pre-existing
  `test_sqlite_store.py`/`test_submission_result_store.py` assertions,
  which still pass untouched).
- Add `_workbook_bytes(workbook)` -- serialize to an in-memory buffer
  (`openpyxl.save` accepts a file-like object) so a route can stream the
  same bytes `save(path)` would write.
- Add `export_application_sessions` + `application_sessions_xlsx_bytes`
  for the dashboard's `ApplicationSession` rows -- a *third* sibling
  export, not a merge, consistent with the deliberate separate-pipeline
  storage convention. List-valued fields (filled/missing/uploaded/
  warnings) become counts or joined text, since a spreadsheet cell can't
  usefully hold a Python list.
- Add `applications_xlsx_bytes`/`submissions_xlsx_bytes` for symmetry.

**`api/routers/export.py` (new):** `GET /export/applications.xlsx` and
`GET /export/submissions.xlsx`. Each reads the caller's own rows
(`by_user(current_user.id)`), builds the workbook in memory, and returns
it as an `.xlsx` attachment. GET-only and read-only -- they never trigger
discovery/preparation/submission and never write to a store, so no
safety gate is involved. They live under `/export` (a binary attachment)
rather than `/api` (JSON), joining `_READ_ONLY_ROUTERS` since they have
no mutating method.

**Frontend:** `services/exportApi.ts` (uses the existing `apiFetch`, so
the access-token + refresh-on-401 logic is reused -- only the response is
a blob, click-downloaded rather than parsed), a reusable
`DownloadExcelButton` with local pending/error state, wired into the
Applications page (applications export) and the History page (submissions
export).

## Consequences

- A dashboard user can download the same formatted, filterable Excel
  workbook the CLI has always produced, scoped to their own data, with no
  terminal -- completing the "store the details in an Excel sheet" step
  of the end-to-end flow entirely in the browser.
- The CLI's `career-agent export` output is unchanged, byte for byte --
  the two existing functions were refactored, not rewritten.
- A third export (`ApplicationSession`) now exists alongside the two
  pipeline-specific ones; a future unified "one application, all
  pipelines" view remains named future work, not attempted here.
- The read-only/GET-only API boundary is preserved: the new routes
  mutate nothing, and the `/api/*` structural proof is untouched (they
  live under `/export`).
