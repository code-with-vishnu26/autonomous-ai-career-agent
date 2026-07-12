# ADR-0077: Notifications & Background Processing

- **Status:** Accepted
- **Date:** 2026-07-13
- **References:** [ADR-0040](0040-notifications-and-observability.md) (the
  existing CLI-only, ephemeral `EventBus`/`Notifier`, never wired to the
  dashboard -- this phase's actual starting point), [ADR-0072](0072-web-dashboard-read-api.md)/[ADR-0074](0074-authentication-and-multi-user-platform.md)
  (the dashboard API and multi-user/JWT model this phase's routers and
  scheduler reuse unchanged), [ADR-0076](0076-production-deployment-and-infrastructure.md)
  (the FastAPI `lifespan` hook this phase's scheduler starts/stops inside,
  and whose own docstring already named "Phase 58" as the email-transport
  gap)

## Context

The user's brief asks for a full event-driven notification platform: a
background scheduler, a `NotificationEngine`/`NotificationDispatcher`/
`NotificationPreferences`/`NotificationTemplates`/`NotificationFormatter`/
`ReminderEngine`/`DigestGenerator`/`NotificationStore`, six notification
types, five-plus delivery channels including Slack/Discord/Teams, 17 named
trigger events, a `ReminderEngine` covering 7 reminder types, daily/weekly/
monthly digests, a full frontend Notification Center, and an ADR numbered
"ADR-0075" -- already taken by the AI Career Coach phase in this same
session; the correct next number is **ADR-0077**.

**A repository-reality audit found the brief names more surface than the
current architecture can honestly support**, the same pattern as Phase 57
(deferred features) and Phase 59 (PostgreSQL). Specifically:

- The existing `EventBus`/`Notifier` (Telegram + ntfy, ADR-0040) is
  CLI-only, constructed fresh per CLI command invocation, and was never
  wired to the FastAPI dashboard at all.
- No scheduler dependency exists anywhere in this codebase.
- No SMTP/email transport exists anywhere -- ADR-0074's own docstring had
  already named this gap as future "Phase 58" work.
- Of the 17 named trigger events, several have no real data source in the
  current dashboard/API architecture: "Jobs discovered" and "Application
  outcome recorded" only exist in CLI-only, dashboard-disconnected
  pipelines; "Interview reminder/tomorrow/today" and "Incomplete profile"
  have no data source (no interview tracking, no per-user profile
  completeness store); "Invitation received/accepted" has no invitation
  system anywhere; "Expired API key" has no expiry concept; "AI Coach
  recommendations available" is purely synchronous request/response with
  no async "available later" state; "Session expired" is already fully
  handled by the existing frontend `SessionExpiredScreen`/
  `SESSION_EXPIRED_EVENT` and needs no new stored notification.
- Slack/Discord/Teams have no existing per-service infrastructure -- the
  brief's own instruction ("only build channels that have existing
  infrastructure, never fabricate integrations") already settles this as
  a deliberate skip, not a scope conflict requiring confirmation.

Given this was the third consecutive phase to hit this exact pattern, and
the user had already twice explicitly endorsed "build what's real, defer
what's not, name it honestly" (Phase 57's and Phase 59's `AskUserQuestion`
answers), this phase's scoping decision was stated directly rather than
asked a third time, and is recorded here for the same transparency.
**Decision: build the trigger events, reminders, and channels that have a
real data source and real infrastructure; name everything else as
deferred, below, rather than fabricating it.**

## Decision

### What actually fires a real notification

Six trigger events have a genuine data source in the current dashboard/
API architecture, and all six are wired for real: résumé prepared
(`cli.py::run_prepare_command`), review approved/rejected
(`run_review_command`), submission completed/cancelled/failed
(`run_submit_command`), and password changed
(`api/routers/auth.py::reset_password`). Every call site wraps its
notification dispatch in a broad `except Exception` -- "notify, never
gate" (ADR-0005's own `NotifyingSubscriber` precedent) means a delivery
failure can never block the underlying prepare/review/submit/password-
reset operation.

### `Notification`/`DeliveryAttempt`: user_id in the row, never the model

`domain/notification.py`'s `Notification` carries no `user_id` field --
the same "denormalize identity, not full content" precedent Phase 56
established for every per-user table; every `SqliteNotificationStore`
method takes `user_id` as a required keyword argument instead.
`NotificationCategory` is a closed `Literal` set matching only the six
real trigger categories above plus three reminder categories and three
digest categories (14 total) -- not the brief's full 17, so an
unsupported category is a type error, not a silent no-op.
`DeliveryStatus = Literal["SENT", "FAILED", "SKIPPED"]` and every
dispatch attempt -- in-app, email, webhook, whichever was actually tried
-- is recorded as a real `DeliveryAttempt` row regardless of outcome.
`SKIPPED` covers "channel disabled," "not configured," and "quiet hours";
none of those is ever silently omitted from the record. This is the
literal implementation of the brief's own "never fabricate delivery
success, record actual delivery status."

### `NotificationDispatcher`: real attempts through real, already-existing infrastructure

`integrations/email.py::SmtpEmailSender` is stdlib `smtplib`/
`email.mime.text` only -- no new email SDK dependency, the same "raw
HTTP/protocol over a dependency SDK" discipline `TelegramNotifier`/
`NtfyNotifier` already hold themselves to. It raises `EmailSendError` on
any failure; it never returns having silently not sent anything.
`integrations/webhook.py::WebhookSender` is a **generic** webhook POST
built on the existing `HttpClient` port -- not three separate Slack/
Discord/Teams SDKs. This is not a workaround for the brief's "only build
channels that have existing infrastructure" instruction; it is exactly
that instruction, read correctly: a Slack/Discord/Teams incoming webhook
*is* an HTTPS POST endpoint, so one generic webhook sender already
satisfies delivering to any of the three, without this codebase needing
to know anything Slack/Discord/Teams-specific. `NotificationDispatcher`
always records in-app first (the notification's own stored row already
*is* the in-app delivery), then attempts email/webhook only if the user's
`NotificationPreferences` enable that channel, want that category
(`wants_category`), and aren't inside their configured quiet hours
(`zoneinfo`-based, handles a midnight-wraparound window, stdlib only).

### `ReminderEngine`/`DigestGenerator`: only the reminders/metrics with a real data source

Of the brief's 7 named reminder types, three have a real data source
today: pending review (`ReviewSession` rows still `WAITING`), pending
submission (approved reviews with no matching `SubmissionResult` yet,
intersected with still-`READY_FOR_REVIEW` application sessions), and
missing Promptfoo validation (`_promptfoo_validated`, reusing
`llm.providers.select_claim_verifier` +
`llm.promptfoo_gate.verify_promptfoo_results` exactly as `cli.py`'s own
verification path does -- no new validation logic). The other four
(interview tomorrow/today, incomplete profile, expired API key) have no
real trigger point and are not built; see "What this phase does not do."
Similarly, the brief's own example digest ("12 new jobs, 4 prepared, 2
awaiting review, 1 submitted, 1 interview scheduled") names two metrics
with no real source -- "new jobs" (discovery is a CLI-only pipeline never
exposed to the dashboard) and "interview scheduled" (no interview-
tracking store exists) -- both omitted, not guessed as zero.
`DigestGenerator` reports exactly the three counts this phase can compute
for real: prepared, awaiting review, submitted.

### `career_agent.scheduler`: top-level, not `core/`, to satisfy the existing layer contract

`APScheduler`'s `AsyncIOScheduler` runs in-process alongside FastAPI's own
event loop (`pyproject.toml`'s `[tool.importlinter]` two contracts --
"dependencies point downward only" and "orchestration never imports a
concrete `ClaimVerifier` directly," ADR-0018/ADR-0043 -- both forbid
anything under `career_agent.core` from importing `career_agent.agents.*`
or (transitively, via `llm.providers`) a concrete `ClaimVerifier`. The
scheduler genuinely needs both, to compose `agents.notifications.*` and
to call `select_claim_verifier` for the Promptfoo-validation reminder.
Rather than weaken either contract, `scheduler.py` lives at
`career_agent.scheduler` -- top-level, sibling to `cli.py` -- exactly
matching how `cli.py` (the existing composition root) is already
unconstrained by both contracts for the identical reason. This is a
reusable pattern: any future module that needs to compose across layers
without itself being an agent belongs at the top level, not inside
`core/`. Six jobs are wired, with fixed ids: `reminders` (interval,
`REMINDER_INTERVAL_MINUTES`), `daily_digest`/`weekly_digest` (cron),
`notification_cleanup` (deletes already-read notifications past
`NOTIFICATION_RETENTION_DAYS`), `expired_token_cleanup` (extends Phase
56's refresh/reset token stores with a real `delete_expired` each),
`retry_failed_webhooks` (retries the latest failed webhook attempt per
user, once, each run). **The scheduler structurally cannot submit
anything** -- proven by an AST-based source scan
(`tests/test_scheduler_purity.py`, the same discipline
`ApplicationPreparationEngine`'s no-submit-selector test and
`ReviewEngine`'s no-browser-import test already established), not merely
a docstring promise: no job function imports `SubmissionEngine`,
`BrowserApplicator`, or any `integrations.browser` symbol, and the source
never calls `.click(` or `.submit(`.

### API: two new write-capable routers, still scoped to the caller's own data

`api/routers/notifications.py` (`GET /notifications`,
`GET /notifications/unread`, `POST /notifications/read`,
`POST /notifications/read-all`, `DELETE /notifications/{id}`) and
`api/routers/notification_settings.py` (`GET`/`PATCH
/notification-settings`, which also carries the caller's webhook URL --
deliberately never echoed back on `GET`, only whether one is configured,
the same discipline this API already applies to secrets) join `/auth/`,
`/user/`, `/coach/` as the only write-capable-router exceptions to the
`/api/*`-is-GET-only structural test (ADR-0072/0074/0075). Every route
requires `get_current_user` and every store method is `user_id`-scoped,
so cross-user notification access is a 404, not a leak -- proven by
dedicated isolation tests in both new router test files.

### Frontend: Notification Bell + Center + Settings + client-side browser push

`NotificationBell` (navbar) polls `/notifications/unread` every 30s via
TanStack Query's `refetchInterval` -- the same "no websockets, no new
real-time transport" shape the rest of this dashboard already commits to.
`NotificationsPage` is the full center: filter (all/unread/read), search,
pagination, mark-read/mark-all-read/delete. `NotificationSettingsPage`
edits channel toggles, reminders/digests toggles, and the webhook URL.
`BrowserNotifier` is the literal implementation of "Browser Notifications
via the browser Notification API, graceful degradation" -- and the exact
file `agents/notifications/dispatcher.py`'s own docstring names as where
that channel actually lives, since there is no server-side "send a
browser notification" action to attempt or log: it shows a small
permission-request banner only while permission is undecided, renders
nothing once granted/denied, and renders nothing at all when
`Notification` is unsupported (`typeof Notification !== "undefined"`,
verified against a real absent-global test case, not just a happy path).

## What this phase explicitly does not do

- **No "jobs discovered" or "application outcome recorded" notifications.**
  Discovery and outcome-recording remain CLI-only, dashboard-disconnected
  pipelines; wiring them would mean changing those pipelines, not adding
  a notification.
- **No interview reminders (tomorrow/today) or incomplete-profile
  reminders.** No interview-tracking store and no per-user profile-
  completeness concept exist anywhere in this codebase.
- **No invitation-received/accepted notifications.** No invitation system
  exists anywhere in this codebase.
- **No expired-API-key notification.** No API-key-expiry concept exists.
- **No "AI Coach recommendations available" notification.** The Career
  Coach (ADR-0075) is purely synchronous request/response; there is no
  async "available later" state to notify about.
- **No new session-expired notification.** Already fully handled by the
  existing frontend `SessionExpiredScreen`/`SESSION_EXPIRED_EVENT`
  (Phase 56); a second, stored notification for the same fact would be
  redundant.
- **No Slack/Discord/Teams-specific SDKs.** The generic `WebhookSender`
  already delivers to any of the three's incoming-webhook URLs; a
  per-service SDK would only be justified by richer formatting
  (attachments, blocks) this phase's brief did not ask for.
- **No "new jobs" or "interview scheduled" digest metrics.** Named above
  under `DigestGenerator` -- no real data source for either.
- **No dedicated notification metrics endpoint.** `/metrics` (ADR-0076)
  already exists; adding notification-specific counters to it is a
  natural, low-risk follow-up, not built in this phase to keep the
  surface reviewable.

## Consequences

- Backend: `domain/notification.py`, `domain/notification_preferences.py`
  (new); `storage/sqlite.py` gains `SqliteNotificationStore`,
  `SqliteNotificationPreferencesStore`, `SqliteDeliveryAttemptStore`,
  `SqliteWebhookSubscriptionStore`, plus `delete_expired` on both token
  stores and `all_users` on `SqliteUserStore`; `agents/notifications/`
  (new package: `engine.py`, `dispatcher.py`, `templates.py`,
  `formatter.py`, `reminder_engine.py`, `digest_generator.py`);
  `integrations/email.py`, `integrations/webhook.py` (new);
  `career_agent/scheduler.py` (new, top-level); `api/routers/
  notifications.py`, `api/routers/notification_settings.py` (new,
  registered as write-capable); `api/app.py`'s `lifespan` starts/stops
  the scheduler; `cli.py`/`api/routers/auth.py` gain notification dispatch
  at their six real trigger points. `Settings` gains `smtp_host`,
  `smtp_port`, `smtp_username`, `smtp_password`, `smtp_use_tls`,
  `smtp_from_address`, `reminder_interval_minutes`,
  `notification_retention_days`. `apscheduler>=3.10` added to the `web`
  extra. New backend tests across domain, storage, the notification
  engine/dispatcher/reminder/digest/templates, both integrations, the
  scheduler's job behavior and structural purity, and both new routers
  (including per-user isolation); full suite, ruff, and both
  import-linter contracts green.
- Frontend: `services/notificationsApi.ts`, `hooks/useNotifications.ts`
  (new); `components/NotificationBell.tsx`, `components/
  BrowserNotifier.tsx` (new); `pages/NotificationsPage.tsx`, `pages/
  NotificationSettingsPage.tsx` (new); wired into `App.tsx`,
  `layouts/Navbar.tsx`, `layouts/AppLayout.tsx`, `layouts/nav-items.ts`.
  New Vitest/RTL tests for the bell, both pages, and browser-notification
  permission states (granted/denied/default/unsupported); `tsc`/
  `oxlint`/`vite build` green.
- Zero changes to `SubmissionEngine`, `BrowserApplicator`, the Human
  Review Center's approval semantics, or any authentication/JWT logic
  beyond adding one notification dispatch call at the end of an already-
  existing `reset_password` handler.

## Future revisit criteria

- If discovery or outcome-recording is ever wired into the dashboard
  (rather than staying CLI-only), the "jobs discovered"/"application
  outcome recorded" notifications become buildable for real at that
  point, not before.
- If an interview-tracking store or a per-user profile-completeness
  concept is ever added to this codebase for its own reasons, the
  corresponding reminder types become buildable for real, reusing
  `ReminderEngine`'s existing shape.
- If richer Slack/Discord/Teams formatting (attachments, interactive
  blocks) is ever genuinely needed, that is a new, explicit per-service
  integration decision -- not a natural extension of the generic
  `WebhookSender`.
- If notification volume or SMTP latency ever becomes a real operational
  concern, `/metrics` (ADR-0076) is the natural place to add delivery/
  retry/latency counters -- revisit then, not speculatively now.
