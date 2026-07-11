"""Excel application-tracker export (Phase 13, ADR-0037; Phase 53, ADR-0071).

The original user requirement from the project's founding brief: one
command, one formatted, filterable openpyxl workbook of every recorded
application -- company, title, source, ATS score, truthfulness verdict,
status, dates, tier used, file paths, latest outcome. Reads the
append-only :class:`~career_agent.storage.sqlite.SqliteApplicationStore`;
never writes back to it.

:func:`export_submissions` (Phase 53) is a separate, sibling sheet-export
for :class:`~career_agent.domain.submission.SubmissionResult` -- kept
distinct from ``export_applications`` rather than merged into one table,
since the two pipelines (``apply``'s ``Application``/``SqliteApplicationStore``
vs. ``prepare``/``review``/``submit``'s ``ApplicationSession``/
``SubmissionResult``) are not the same rows and were never unified
(ADR-0069/0070/0071 each note this as a deliberate, separate storage
convention). A future combined view is named future work, not attempted
here.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

if TYPE_CHECKING:
    from career_agent.domain.submission import SubmissionResult

_COLUMNS: list[tuple[str, str]] = [
    ("recorded_at", "Recorded"),
    ("company", "Company"),
    ("title", "Title / Summary"),
    ("source", "Source"),
    ("status", "Status"),
    ("truthfulness_approved", "Truthfulness"),
    ("ats_total", "ATS Score"),
    ("tier_used", "Tier"),
    ("profile_version", "Profile Version"),
    ("prompt_version", "Prompt Version"),
    ("artifact_paths", "Files"),
    ("latest_outcome", "Latest Outcome"),
]


def export_applications(rows: list[dict[str, object]], path: Path) -> Path:
    """Write ``rows`` (from ``SqliteApplicationStore.all_rows``) to ``path``.

    Returns the written path. Boolean-ish integers are rendered as
    approved/blocked so a human reads the sheet without decoding; the
    header row is bold and frozen, and an auto-filter spans the table --
    "formatted, filterable" per the founding requirement.
    """
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Applications"

    for column_index, (_key, label) in enumerate(_COLUMNS, start=1):
        cell = sheet.cell(row=1, column=column_index, value=label)
        cell.font = Font(bold=True)

    for row_index, row in enumerate(rows, start=2):
        for column_index, (key, _label) in enumerate(_COLUMNS, start=1):
            value = row.get(key)
            if key == "truthfulness_approved":
                value = "approved" if value else "blocked"
            sheet.cell(row=row_index, column=column_index, value=value)

    last_column = get_column_letter(len(_COLUMNS))
    sheet.auto_filter.ref = f"A1:{last_column}{max(len(rows) + 1, 1)}"
    sheet.freeze_panes = "A2"
    for column_index in range(1, len(_COLUMNS) + 1):
        sheet.column_dimensions[get_column_letter(column_index)].width = 18

    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)
    return path


_SUBMISSION_COLUMNS: list[tuple[str, str]] = [
    ("submitted_at", "Submitted"),
    ("company", "Company"),
    ("job_title", "Role"),
    ("provider", "Provider"),
    ("status", "Status"),
    ("submitted", "Submitted?"),
    ("confirmation_id", "Confirmation ID"),
    ("duration_seconds", "Duration (s)"),
    ("refusal_reason", "Refusal Reason"),
    ("warnings", "Warnings"),
]


def export_submissions(results: list[SubmissionResult], path: Path) -> Path:
    """Write ``results`` to ``path``.

    From ``SqliteSubmissionResultStore.all_results`` -- same formatted/
    filterable shape as ``export_applications`` (Phase 53, ADR-0071), a
    separate sheet/file since the two pipelines track different rows.
    """
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Submissions"

    for column_index, (_key, label) in enumerate(_SUBMISSION_COLUMNS, start=1):
        cell = sheet.cell(row=1, column=column_index, value=label)
        cell.font = Font(bold=True)

    for row_index, result in enumerate(results, start=2):
        row = result.model_dump()
        row["warnings"] = "; ".join(result.warnings)
        for column_index, (key, _label) in enumerate(_SUBMISSION_COLUMNS, start=1):
            value = row.get(key)
            if key == "submitted":
                value = "yes" if value else "no"
            sheet.cell(row=row_index, column=column_index, value=str(value or ""))

    last_column = get_column_letter(len(_SUBMISSION_COLUMNS))
    sheet.auto_filter.ref = f"A1:{last_column}{max(len(results) + 1, 1)}"
    sheet.freeze_panes = "A2"
    for column_index in range(1, len(_SUBMISSION_COLUMNS) + 1):
        sheet.column_dimensions[get_column_letter(column_index)].width = 18

    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)
    return path
