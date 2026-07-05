"""Local Streamlit dashboard over the SQLite metrics (Phase 16, ADR-0040).

Run with::

    streamlit run src/career_agent/dashboard.py

Local-only, read-only, no auth complexity by design: it reads the same
SQLite file the CLI writes and renders discovery counts by source, gate
pass/block rates (truthfulness AND ATS), ATS score distribution, the
application funnel, and the human-approval trail. All data preparation
lives in :func:`dashboard_metrics` -- a pure function over plain rows,
fully tested without Streamlit; only the thin rendering shell below
requires the optional ``streamlit`` dependency (``pip install
career-agent[dashboard]``).

This module reads the database directly (its own SQL) rather than through
``OpportunityRepository`` -- deliberately: the repository contract stays
exactly ``add``/``get`` (ADR-0037's fidelity guard), and a read-only local
viewer is a separate read model, not a new contract method.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path

from pydantic import BaseModel, Field

from career_agent.agents.learning.funnel import (
    build_funnel_report,
    render_funnel_report,
)


class DashboardMetrics(BaseModel):
    """Everything the dashboard renders, computed purely from rows."""

    discovery_by_source: dict[str, int] = Field(default_factory=dict)
    applications_total: int = 0
    truthfulness_approved: int = 0
    truthfulness_blocked: int = 0
    ats_scores: list[float] = Field(default_factory=list)
    funnel_text: str = ""


def _read_opportunity_sources(database_path: Path) -> list[str]:
    if not database_path.exists():
        return []
    with sqlite3.connect(database_path) as connection:
        try:
            rows = connection.execute(
                "SELECT payload FROM opportunities"
            ).fetchall()
        except sqlite3.OperationalError:
            return []
    sources = []
    for (payload,) in rows:
        try:
            sources.append(str(json.loads(payload).get("source", "unknown")))
        except (json.JSONDecodeError, AttributeError):
            sources.append("unknown")
    return sources


def dashboard_metrics(
    database_path: Path,
    application_rows: list[dict[str, object]],
    outcome_rows: list[dict[str, object]],
) -> DashboardMetrics:
    """Pure metric computation -- testable with no Streamlit anywhere."""
    approved = sum(
        1 for row in application_rows if row.get("truthfulness_approved")
    )
    return DashboardMetrics(
        discovery_by_source=dict(Counter(_read_opportunity_sources(database_path))),
        applications_total=len(application_rows),
        truthfulness_approved=approved,
        truthfulness_blocked=len(application_rows) - approved,
        ats_scores=[
            float(row["ats_total"])
            for row in application_rows
            if row.get("ats_total") is not None
        ],
        funnel_text=render_funnel_report(
            build_funnel_report(application_rows, outcome_rows)
        ),
    )


def main() -> None:  # pragma: no cover -- thin shell over tested metrics
    """Render the dashboard (requires the optional streamlit dependency)."""
    import streamlit as st

    from career_agent.core.config import Settings
    from career_agent.storage.sqlite import SqliteApplicationStore

    settings = Settings()
    database_path = Path(settings.database_path)
    store = SqliteApplicationStore(database_path)
    metrics = dashboard_metrics(
        database_path, store.all_rows(), store.outcome_rows()
    )

    st.title("Career Agent — local dashboard")
    st.caption("Read-only view over the local SQLite store. No network.")

    st.subheader("Discovery by source")
    if metrics.discovery_by_source:
        st.bar_chart(metrics.discovery_by_source)
    else:
        st.write("No opportunities discovered yet.")

    st.subheader("Gates")
    left, right = st.columns(2)
    left.metric("Truthfulness approved", metrics.truthfulness_approved)
    right.metric("Truthfulness blocked", metrics.truthfulness_blocked)

    st.subheader("ATS score distribution")
    if metrics.ats_scores:
        st.bar_chart(
            Counter(int(score // 10) * 10 for score in metrics.ats_scores)
        )
    else:
        st.write("No ATS-scored applications yet.")

    st.subheader("Funnel (raw counts — ADR-0039)")
    st.text(metrics.funnel_text)


if __name__ == "__main__":  # pragma: no cover
    main()
