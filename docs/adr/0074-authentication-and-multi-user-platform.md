# ADR-0074: Authentication & Multi-User Platform

- **Status:** Accepted
- **Date:** 2026-07-11
- **References:** [ADR-0072](0072-web-dashboard-read-api.md)/[ADR-0073](0073-react-dashboard-frontend.md)
  (the dashboard this phase adds accounts to), [ADR-0064](0064-job-search-preferences-separate-from-profile.md)
  (`JobPreferences`, reused unmodified as the per-user preferences payload)

## Context

The dashboard (Phases 54-55) is fully built but single-user: every row in
every table belongs to whoever happens to run `career-agent serve`, with
no login, no account, and no way for a second person to have their own
data. The user's brief asks for a real multi-user platform: JWT auth
(access + refresh tokens), password hashing, protected routes on both the
API and the frontend, per-user ownership of every existing table, a
migration for pre-existing single-user databases, and account/preference
management pages.

This is the largest architectural change since the project began — the
first time this codebase has ever needed to distinguish "whose data is
this." It's scoped deliberately: real, working auth end-to-end, proven
against a live browser session (not just unit tests), with every deferred
piece named rather than silently absent.

## Decision

### `user_id` lives in the SQL row, never on the domain model

`ApplicationSession`/`ReviewSession`/`SubmissionResult`/`ResumeVariant`
(Phases 50-53) stay exactly as they were — pure, storage-agnostic Pydantic
models, unchanged. Ownership is a `user_id` column on each table, set via
a new required keyword-only `user_id` argument on each store's `save()`
(no default — a missing owner is a `TypeError` at every call site, not a
silent cross-user leak) and read via a new `by_user(user_id)` method
mirroring the existing `by_opportunity`/`by_category` pattern. This is the
same "denormalize identity fields, not full content" precedent
`SqliteApplicationStore`'s own `company`/`title` columns already set
(Phases 50-53's own ADRs) — extended one column wider, not a new pattern.
The alternative (adding `user_id` as a domain-model field) was rejected:
it would have forced a breaking-constructor change through every one of
Phases 50-53's ~40 existing tests for no benefit a storage-layer parameter
doesn't already provide.

### `domain/` stays free of `bcrypt`/`jwt` -- password/token logic lives in `core/`

`tests/domain/test_purity.py` enforces that every `domain/` module imports
only the standard library or Pydantic. Password hashing and JWT encode/
decode are exactly the kind of external, replaceable mechanism `domain/`
is supposed to stay ignorant of — the same reasoning that already keeps
LLM clients and browser automation out of it. `core/security.py` (not
`domain/auth.py`, corrected mid-implementation when the purity test
caught the violation) holds `hash_password`/`verify_password`
(bcrypt), `create_access_token`/`decode_access_token` (PyJWT,
`HS256`), and `generate_refresh_token_value`/`hash_opaque_token`
(cryptographically random opaque strings, SHA-256-hashed before storage —
never bcrypt for these: they're already 256+ bits of entropy, unlike a
human password, so a slow KDF only slows the login-refresh hot path for
no security benefit). `domain/user.py::User` stays pure data.

### Access token in the response body; refresh token in an httpOnly cookie

Access tokens (15 min default) are signed JWTs carrying `sub`/`role`,
returned in the JSON body and held by the frontend **in memory only**
(`services/tokenStore.ts`) — never `localStorage`, so an XSS payload that
can run a script can steal the current token but nothing that survives a
reload. Refresh tokens (30 days default) are opaque random strings, never
JWTs, persisted server-side only as a SHA-256 hash
(`SqliteRefreshTokenStore`) and delivered exclusively via an httpOnly,
`SameSite=Lax` cookie scoped to `/auth` — never sent as a header, never
readable by JavaScript. Refresh **rotates on every use**: the presented
token is revoked the instant a replacement is issued, so a stolen,
replayed refresh token works at most once before the legitimate rotation
invalidates it. No CSRF token: `SameSite=Lax` already blocks cross-site
POST (only top-level GET navigations are exempt), and `/auth/refresh`
itself does nothing a blind cross-site trigger could exploit.

### Fail-closed JWT secret

`Settings.jwt_secret_key` has no default. `api/security.py::require_jwt_secret`
raises a `500` (not a more specific 4xx — an unconfigured secret is a
deployment misconfiguration, not a caller error) if it's unset, so the API
never silently signs tokens with a shared, guessable value every install
would otherwise carry.

### CLI stays single-operator; the dashboard becomes multi-user

The CLI has no login flow — it's a local terminal, not a browser session.
`career-agent prepare`/`review`/`submit` now call
`storage.sqlite.migrate_to_multi_user()` at the start of each command,
which auto-provisions (once, idempotently) a single, real "local operator"
account keyed by `Settings.cli_local_user_email`, and resolves its id for
every `save()` call. Multiple distinct humans sharing one CLI install
remains out of scope — multiple humans using the *dashboard* is exactly
what this phase adds. The same function also handles migrating a
pre-Phase-56 database: it adds the `user_id` column to each of the four
tables via `ALTER TABLE` (a fresh `CREATE TABLE IF NOT EXISTS` is a no-op
against an existing table, so the column has to be added explicitly) and
backfills every `NULL`-owned row — i.e. every row that predates this
phase — to the local operator account. Idempotent and safe to call on
every process startup.

### Every existing dashboard route now requires auth and filters by owner

`applications`/`reviews`/`submissions`/`resume-variants`/`analytics`/`settings`
(Phase 54) all gained a `current_user: User = Depends(get_current_user)`
parameter and switched from `all_*()` to `by_user(current_user.id)`. A
dedicated test (`test_applications_never_returns_another_users_data`)
seeds two owners and asserts a caller only ever sees their own rows.
`GET /api/settings` additionally gained `jwt_secret_key` to its redaction
list — a real gap caught while wiring this phase: the signing key itself
would otherwise have been the one secret this endpoint leaked, and leaking
it lets a caller forge a token for any user id.

### New routers: `/auth/*` and `/user/*`

`POST /auth/register|login|logout|refresh`, `GET /auth/me`,
`POST /auth/forgot-password|reset-password`; `PUT /user/profile`,
`GET`/`PUT /user/preferences`. These are the only two write-capable
routers this API has ever had — every other route stays `GET`-only,
proven structurally (`test_auth_and_user_are_the_only_write_capable_routers`
enumerates every route the app registers and asserts any mutating method
is confined to `/auth/`/`/user/`). `forgot-password` always returns `202`
regardless of whether the email is registered (never lets a caller
enumerate accounts); it issues and stores a real, hashed, time-limited
reset token, but **does not send an email** — no transport exists yet
(Phase 58, Notifications). Faking a "check your inbox" response without a
real send would be exactly the kind of unverified capability claim this
project's discipline has refused every phase so far.

### Minimal in-memory rate limiter on auth endpoints

`api/rate_limit.py::InMemoryRateLimiter` — a fixed-window counter per
client IP, process-local, applied to `register`/`login`/`forgot-password`
(5 requests/minute). Deliberately not Redis-backed: this is a
single-process `uvicorn` deployment with no multi-instance story yet: a
process-local dict is a real, correct limiter for that shape, not a
placeholder for one. Redis belongs with the eventual multi-instance
deployment story (Phase 59), not bolted on before anything needs more than
one process.

### `JobPreferences` gets a second, per-user home

`SqliteUserPreferencesStore` stores one `JobPreferences` (Phase 46,
ADR-0064, reused unmodified) row per dashboard user, upserted via
`PUT /user/preferences`. The CLI's existing file-based
`storage/job_preferences.py` (`job_preferences.json`) is untouched and
still exactly what `career-agent preferences`/`discover` use for the
local operator — this is the dashboard's per-user analogue, not a
replacement.

### A real concurrency bug found and fixed during browser verification

Manual end-to-end testing (Playwright against a live `career-agent serve`
+ Vite dev server) caught a genuine race: React's Strict Mode
deliberately double-invokes effects in development, and `AuthProvider`'s
initial-session-restore effect called `/auth/refresh` on mount. Combined
with refresh-token rotation-on-use, the two invocations raced — the first
successfully rotated the cookie, the second (using the now-stale,
already-revoked cookie) got a `401` and the login-restoring `setUser` call
was the one that "won," losing a session that had, milliseconds earlier,
been correctly restored. Fixed with a `useRef`-memoized in-flight promise
so both Strict Mode invocations share one real request instead of each
firing its own (`AuthContext.tsx`); a regression test renders the provider
inside `<StrictMode>` and asserts exactly one `/auth/refresh` call
reaches the network. This is the kind of defect that unit tests mocking
`fetch` per-call would never have surfaced — only driving a real browser
against a real backend found it, which is why that verification step
stayed in the loop for this phase despite the extra time it took.

### Frontend: `AuthProvider`, `ProtectedRoute`, a refresh-aware fetch wrapper

`services/http.ts::apiFetch` attaches the access token, always sends
`credentials: "include"`, and transparently retries a `401` once via
`/auth/refresh` before giving up and dispatching a
`career-agent:session-expired` window event (`AuthContext` listens for it
and renders `SessionExpiredScreen` — the brief's "session timeout
screen"). `ProtectedRoute` redirects to `/login` when there's no session,
preserving the intended destination. New pages: `LoginPage`,
`RegisterPage`, `ForgotPasswordPage`, `ResetPasswordPage`, `ProfilePage`
(display name), `AccountPage` (role/member-since/logout — no in-app
change-password form yet, since the only password-change path today is
the reset-token flow). `ThemeProvider` was added to lift dark-mode state
to the app root — the existing per-`Navbar`-instance `useTheme()` call
(Phase 55) meant dark mode never applied on the public auth pages at all
(they mount outside `AppLayout`/`Navbar` entirely), a second real gap
found during the same browser verification pass.

## What this phase explicitly does not do

- No email delivery for password resets (Phase 58).
- No Redis-backed rate limiting or multi-instance deployment story
  (Phase 59).
- No Postgres — the brief asked for "multi-user SQLite/Postgres," and one
  SQLite file with per-row ownership fully satisfies the actual
  requirement (multiple accounts, isolated data) without a database
  migration this project's actual (single-install, personal-scale) usage
  doesn't yet justify.
- No admin capability. `User.role` includes `"admin"` and
  `api/security.py::require_admin` exists, but nothing grants an admin
  elevated data access yet — every route still filters by the caller's
  own `user_id` regardless of role.
- No in-app change-password form (only reset-via-token).
- No organizations/teams/billing (Phase 60).

## Consequences

- Backend: 79 new tests (`core/test_security.py`,
  `domain/test_user.py`, `storage/test_user_store.py`, `api/test_auth.py`,
  `api/test_user_router.py`, `test_cli_local_operator.py`, plus per-user
  isolation/auth-boundary additions to `test_dashboard_api.py`); full
  suite green. Frontend: 13 new tests (`services/http.test.ts`,
  `pages/auth/LoginPage.test.tsx`, `components/ProtectedRoute.test.tsx`,
  `context/AuthContext.test.tsx`'s Strict-Mode regression test), full
  suite green, clean `tsc`/`oxlint`/`vite build`.
- Manually verified end-to-end against a real running backend + Vite dev
  server with Playwright: register → dashboard (per-user, empty for a
  fresh account) → profile update → reload (session persists via the
  refresh cookie) → account page → logout → redirect to `/login`; dark
  mode confirmed on both the authenticated app and the public login page.
- Zero changes to `ApplicationSession`/`ReviewSession`/`SubmissionResult`/
  `ResumeVariant` themselves, to `SubmissionEngine`/`ReviewEngine`/
  `ApplicationPreparationEngine`, or to any Phase 50-53 test.

## Future revisit criteria

- If a genuine admin capability is ever needed (viewing another user's
  data for support, moderation), design that access path explicitly then
  — `require_admin` existing today is not itself authorization for
  anything.
- If this ever needs more than one `uvicorn` process/instance, the
  in-memory rate limiter and any in-process assumption need a real
  distributed replacement (Redis), not a bigger in-memory dict.
- If Phase 58 (Notifications) ships a real email/notification transport,
  wire `forgot-password` to it and delete the "no email sent yet" caveat
  from both the API docstring and the frontend `ForgotPasswordPage`
  copy.
- If a second frontend or a non-browser API client ever needs write
  access without cookies (e.g. a CLI-driven login), the refresh-via-
  httpOnly-cookie design would need an alternative delivery path for that
  client — not a reason to weaken it for the browser case.
