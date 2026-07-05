# ADR-0040: Notifications (Telegram + ntfy fallback) and the local Streamlit dashboard

- **Status:** Accepted
- **Date:** 2026-07-04
- **References:** [ADR-0005](0005-event-bus.md) (events notify, never gate
  — the rule notifications live and die by), [ADR-0039](0039-learn-pillar.md)
  (whose caveat travels into the dashboard's funnel view unchanged)

## Decision

**`Notifier` port + two real implementations**
(`integrations/notifications.py`), both through the existing `HttpClient`
port (fixture-tested, zero network in the suite): `TelegramNotifier`
(Bot API `sendMessage`; the token is in Telegram's URL scheme by API
design but is never logged, never stored, and elided from error text —
the original URL-bearing exception is deliberately not chained; tested)
and `NtfyNotifier` (zero-setup fallback: JSON publish to a topic).

**`NotifyingSubscriber`: notify, never gate — injection-verified.** It
subscribes to `HumanActionRequired` / `ApplicationFailed` /
`OutcomeRecorded` on the bus and swallows delivery failures with a log
line: a dead Telegram bot must never block or fail a submission flow.
Making the failure propagate was caught by the dedicated test. Wired at
the composition root (`build_notifier`: Telegram when configured, else
ntfy, else nothing).

**Local Streamlit dashboard** (`dashboard.py`, `streamlit run
src/career_agent/dashboard.py`, optional `[dashboard]` extra): read-only,
local-only, no auth complexity by design. All data preparation is
`dashboard_metrics` — a pure, fully-tested function over plain rows
(discovery counts by source, truthfulness pass/block, ATS score
distribution, the ADR-0039 funnel with its caveat intact); only the thin
rendering shell needs Streamlit and is excluded from coverage as a named
boundary. It reads the SQLite file directly as a separate read model —
deliberately, so the repository contract stays exactly `add`/`get`
(ADR-0037's fidelity guard is untouched).

## Future revisit criteria

- High-match-found notifications from `discover` (needs the notifier
  wired into the discover path — trivial once wanted).
- Cost/token-per-application metrics need real cost accounting on LLM
  calls first — named, unbuilt.
