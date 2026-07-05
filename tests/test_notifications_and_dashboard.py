"""Phase 16 / ADR-0040: notifications (notify, never gate) + dashboard metrics."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from career_agent.core.events import ApplicationFailed, HumanActionRequired
from career_agent.dashboard import dashboard_metrics
from career_agent.integrations.notifications import (
    Notifier,
    NotifyingSubscriber,
    NtfyNotifier,
    TelegramNotifier,
)
from tests._fakes import FakeHttpClient


async def test_telegram_sends_and_never_leaks_the_token_in_errors():
    client = FakeHttpClient(default={"ok": True})
    notifier = TelegramNotifier(
        bot_token="SECRET-TOKEN", chat_id="42", client=client
    )
    await notifier.notify("Title", "Body")
    url, body = client.post_calls[0]
    assert "SECRET-TOKEN" in url  # Telegram's own URL scheme requires it
    assert body["chat_id"] == "42"
    assert "Title" in body["text"]

    class _Boom:
        async def post_json(self, url, *, json, headers=None):
            raise RuntimeError(f"failed calling {url}")  # would leak the URL

        async def get_json(self, url, *, params=None, headers=None):
            raise NotImplementedError

    failing = TelegramNotifier(bot_token="SECRET-TOKEN", chat_id="42", client=_Boom())
    try:
        await failing.notify("t", "m")
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "SECRET-TOKEN" not in str(exc)  # token elided from the error
        assert exc.__cause__ is None  # original URL-bearing error not chained


async def test_ntfy_publishes_to_the_topic():
    client = FakeHttpClient(default={})
    await NtfyNotifier(topic="my-topic", client=client).notify("T", "M")
    _url, body = client.post_calls[0]
    assert body == {"topic": "my-topic", "title": "T", "message": "M"}


async def test_subscriber_notifies_on_pause_and_failure_and_never_raises():
    sent: list[tuple[str, str]] = []

    class _Recorder:
        async def notify(self, title: str, message: str) -> None:
            sent.append((title, message))

    subscriber = NotifyingSubscriber(_Recorder())
    await subscriber(
        HumanActionRequired(
            correlation_id="c", application_id="app-1", reason="verification"
        )
    )
    await subscriber(
        ApplicationFailed(
            correlation_id="c",
            application_id="app-1",
            tier_attempted="browser",
            error_category="timeout",
        )
    )
    assert len(sent) == 2
    assert "paused" in sent[0][1]

    class _Broken:
        async def notify(self, title: str, message: str) -> None:
            raise RuntimeError("telegram down")

    broken = NotifyingSubscriber(_Broken())
    # Must swallow -- notify, never gate (ADR-0005).
    await broken(
        HumanActionRequired(
            correlation_id="c", application_id="app-1", reason="captcha"
        )
    )


def test_notifier_protocol_satisfied():
    client = FakeHttpClient(default={})
    assert isinstance(
        TelegramNotifier(bot_token="t", chat_id="c", client=client), Notifier
    )
    assert isinstance(NtfyNotifier(topic="t", client=client), Notifier)


def test_dashboard_metrics_pure_computation(tmp_path: Path):
    db = tmp_path / "db.sqlite"
    with sqlite3.connect(db) as connection:
        connection.execute(
            "CREATE TABLE opportunities (id TEXT PRIMARY KEY, fingerprint TEXT,"
            " authoritative INTEGER, payload TEXT)"
        )
        for index, source in enumerate(["job_board", "job_board", "ats_api"]):
            connection.execute(
                "INSERT INTO opportunities VALUES (?, ?, 1, ?)",
                (f"o{index}", f"f{index}", json.dumps({"source": source})),
            )
    application_rows = [
        {
            "id": "a1",
            "prompt_version": "p1",
            "profile_version": "v1",
            "truthfulness_approved": 1,
            "ats_total": 81.0,
        },
        {
            "id": "a2",
            "prompt_version": "p1",
            "profile_version": "v1",
            "truthfulness_approved": 0,
            "ats_total": None,
        },
    ]
    metrics = dashboard_metrics(db, application_rows, [])
    assert metrics.discovery_by_source == {"job_board": 2, "ats_api": 1}
    assert metrics.applications_total == 2
    assert metrics.truthfulness_approved == 1
    assert metrics.truthfulness_blocked == 1
    assert metrics.ats_scores == [81.0]
    assert "CAVEAT" in metrics.funnel_text  # the honesty caveat travels here too


def test_dashboard_metrics_handles_missing_database(tmp_path: Path):
    metrics = dashboard_metrics(tmp_path / "missing.sqlite", [], [])
    assert metrics.discovery_by_source == {}
    assert metrics.applications_total == 0
