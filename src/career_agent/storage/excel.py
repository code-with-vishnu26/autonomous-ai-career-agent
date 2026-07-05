"""Excel application-tracker export (Phase 13, ADR-0037).

The original user requirement from the project's founding brief: one
command, one formatted, filterable openpyxl workbook of every recorded
application -- company, title, source, ATS score, truthfulness verdict,
status, dates, tier used, file paths, latest outcome. Reads the
append-only :class:`~career_agent.storage.sqlite.SqliteApplicationStore`;
never writes back to it.
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

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
