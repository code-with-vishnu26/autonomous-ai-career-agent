"""SqliteSubscriptionStore + SqliteUsageCounterStore (Phase 60, ADR-0078).

Backs the billing stub -- see ``domain/billing.py`` and
``integrations/billing.py`` for why this is deliberately not Stripe.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from career_agent.domain.billing import Subscription, UsageCounter
from career_agent.storage.sqlite import _connect

_SUBSCRIPTION_SCHEMA = """
CREATE TABLE IF NOT EXISTS subscriptions (
    organization_id TEXT PRIMARY KEY,
    payload TEXT NOT NULL
);
"""

_USAGE_COUNTER_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_counters (
    organization_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (organization_id, metric)
);
"""


class SqliteSubscriptionStore:
    """One subscription record per organization -- upsert-one-row-per-key."""

    def __init__(self, path: Path) -> None:
        """Open (creating if needed) the SQLite database at ``path``."""
        self._path = path
        with _connect(path) as connection:
            connection.executescript(_SUBSCRIPTION_SCHEMA)

    def save(self, subscription: Subscription) -> None:
        """Upsert one organization's subscription."""
        with _connect(self._path) as connection:
            connection.execute(
                "INSERT INTO subscriptions (organization_id, payload) VALUES (?, ?)"
                " ON CONFLICT(organization_id) DO UPDATE SET"
                " payload = excluded.payload",
                (subscription.organization_id, subscription.model_dump_json()),
            )

    def get(self, organization_id: str) -> Subscription | None:
        """``organization_id``'s subscription, or ``None`` if never set."""
        with _connect(self._path) as connection:
            row = connection.execute(
                "SELECT payload FROM subscriptions WHERE organization_id = ?",
                (organization_id,),
            ).fetchone()
        return Subscription.model_validate(json.loads(row["payload"])) if row else None


class SqliteUsageCounterStore:
    """One counter per (organization, metric) -- upsert-one-row-per-key."""

    def __init__(self, path: Path) -> None:
        """Open (creating if needed) the SQLite database at ``path``."""
        self._path = path
        with _connect(path) as connection:
            connection.executescript(_USAGE_COUNTER_SCHEMA)

    def increment(
        self, *, organization_id: str, metric: str, now: datetime, by: int = 1
    ) -> UsageCounter:
        """Increment (or start) one metric's counter and return the new total."""
        existing = self.get(organization_id=organization_id, metric=metric)
        updated = UsageCounter(
            organization_id=organization_id,
            metric=metric,
            count=(existing.count if existing else 0) + by,
            period_start=existing.period_start if existing else now,
        )
        with _connect(self._path) as connection:
            connection.execute(
                "INSERT INTO usage_counters (organization_id, metric, payload)"
                " VALUES (?, ?, ?)"
                " ON CONFLICT(organization_id, metric) DO UPDATE SET"
                " payload = excluded.payload",
                (organization_id, metric, updated.model_dump_json()),
            )
        return updated

    def get(self, *, organization_id: str, metric: str) -> UsageCounter | None:
        """One metric's current counter, or ``None`` if never incremented."""
        with _connect(self._path) as connection:
            row = connection.execute(
                "SELECT payload FROM usage_counters"
                " WHERE organization_id = ? AND metric = ?",
                (organization_id, metric),
            ).fetchone()
        return UsageCounter.model_validate(json.loads(row["payload"])) if row else None

    def by_organization(self, organization_id: str) -> list[UsageCounter]:
        """Every metric currently tracked for one organization."""
        with _connect(self._path) as connection:
            rows = connection.execute(
                "SELECT payload FROM usage_counters WHERE organization_id = ?",
                (organization_id,),
            ).fetchall()
        return [UsageCounter.model_validate(json.loads(row["payload"])) for row in rows]
