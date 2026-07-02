"""Persistence: SQLite as the system of record, openpyxl for spreadsheet exports.

SQLite holds opportunities, applications, and outcomes; openpyxl produces
human-readable trackers the user can audit.

``profile.py`` (Phase 6, ADR-0017) is a different kind of persistence read: a
one-shot loader/validator for the user's JSON Resume master profile file, not
part of the SQLite system-of-record.
"""
