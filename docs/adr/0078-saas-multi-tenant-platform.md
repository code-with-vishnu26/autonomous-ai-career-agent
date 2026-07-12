# ADR-0078: SaaS Multi-Tenant Platform (Organizations & RBAC)

- **Status:** Accepted
- **Date:** 2026-07-12
- **References:** [ADR-0000](0000-project-philosophy.md) (this ADR partially
  supersedes its "Multi-tenancy or a hosted SaaS" non-goal -- see below),
  [ADR-0074](0074-authentication-and-multi-user-platform.md) (the JWT/
  multi-user model this phase reuses unchanged; its own summary already
  named "no organizations/billing (Phase 60)" as future work), [ADR-0077](0077-notifications-and-background-processing.md)
  (the `NotificationEngine`/`EmailSender` this phase's invitation delivery
  reuses; also the ADR that first deferred "invitation received" for
  having no invitation system -- this phase builds one for real)

## Context

The brief asks for a full transformation: every user belongs to an
Organization; Organizations own applications/notifications/résumés/
reviews/settings/team members; five roles (owner/admin/recruiter/member/
viewer) with a fixed permission matrix; a real invitation system; a
production-ready billing abstraction (explicitly not Stripe); an audit
log; a platform-admin surface; and 120+ new tests.

**This is a different kind of gap than Phases 57/58/59 hit.** Those were
"the brief names more features than the architecture currently supports"
-- build the real subset, defer the rest, name it. This phase's audit
found something categorically different: **[ADR-0000](0000-project-philosophy.md)**,
this project's own foundational document, explicitly rules out
multi-tenancy "by fiat" --

> Some attractive features (mass apply, multi-tenant) are ruled out by
> fiat; contributors must internalize the rules rather than chase local
> wins.

-- and names its own revisit trigger, verbatim:

> Revisit this philosophy if: The project's intended audience changes from
> single self-hosted user to a hosted / multi-user product (would
> invalidate several non-goals).

That is exactly what this phase's brief asks for. Building it without
surfacing this would either silently contradict the project's own root
document, or require unilaterally deciding a mission change no prior
phase's audit was authorized to make. This was surfaced to the user
directly (not folded into a third scoping `AskUserQuestion` of the "which
subset" kind Phases 57/59 used -- this is a different, higher-stakes
question: not "how much of this feature," but "should the project's
stated mission change at all"). **The user confirmed: proceed, and amend
ADR-0000** rather than build silently against a document that would then
misdescribe the codebase. ADR-0000 itself is not rewritten (this
project's ADRs are immutable once accepted); its Status line and "Future
revisit criteria" section instead point here, the same "Amends ADR-XXXX"
precedent [ADR-0057](0057-ci-and-cross-platform-release-hardening.md)
already established for updating a claim from reasoning to evidence.

**One more real tension in the brief itself, resolved before writing
code:** it says both "every query must become `organization_id` +
`user_id`, never rely on `user_id` alone" **and** "reuse every existing
backend service... do not rewrite the Submission Engine, Review Engine,
Notification Engine, Resume Engine, Career Coach, Scheduler, FastAPI
application, Authentication." Retrofitting `organization_id` onto the
nine pre-existing personal-resource tables (résumé variants, application
sessions, review sessions, submission results, notifications, and four
more) would mean touching every one of those services' stores and every
router built on them -- directly the rewrite the brief's own instruction
forbids. The brief's own file list under "Build > Backend > Create" also
only lists *new* files (organizations/team/roles domain+storage+routers),
never touching the existing nine. Read together, the intended scope is:
**every genuinely new piece of data this phase introduces is
organization_id+user_id scoped from creation; the nine pre-existing
personal-resource tables stay user_id-scoped exactly as before**, named
explicitly below rather than silently narrowed.

## Decision

### Organization/Membership/Role/Permission: new data, organization_id+user_id from creation

`domain/organization.py` (`Organization`), `domain/team.py`
(`Membership`, `Invitation`), `domain/roles.py` (`Role`,
`Permission`, the fixed `ROLE_PERMISSIONS` mapping), `domain/audit.py`
(`AuditLogEntry`), `domain/billing.py` (`Plan`, `Subscription`,
`UsageCounter`) -- all pure Pydantic models, no bcrypt/JWT/DB import, the
same purity `import-linter`'s "domain depends on nothing else" contract
already enforces for `domain/user.py`. `Role` is deliberately a second,
separate concept from `domain.user.UserRole` (`"user" | "admin"`, an
unused-until-now platform-wide flag from Phase 56) -- one is a per-
organization context role, the other a platform-operator flag; conflating
them would make "give someone dashboard-wide admin" and "make someone an
org's admin" the same action, which they must never be.

Every registered account gets a **real personal organization** at
registration (`career_agent/organizations.py::create_personal_organization`,
called from `POST /auth/register`) -- owner role, slug derived from the
email's local part. This is how "every user belongs to an organization"
holds without a forced org-creation step. Pre-Phase-60 accounts are
backfilled the same way via `migrate_users_without_organization`, called
idempotently from the FastAPI `lifespan` hook on every startup -- the
exact same "`ALTER TABLE`-if-missing, backfill `NULL` rows, never orphan
history, safe to re-run" discipline `storage.sqlite.migrate_to_multi_user`
already established for the Phase 56 multi-user migration.

### RBAC: no JWT claim change, a real per-request membership lookup instead

`api/rbac.py` provides exactly the three dependencies the brief names --
`require_membership` (`OrganizationRequired`), `require_permission(...)`
(`PermissionRequired`), `require_role(...)` (`RoleRequired`) -- as
dependency *factories* every organization-scoped route depends on, never
re-implementing the check inline ("never duplicate route authorization").
Deliberately **no `organization_id` JWT claim**: adding one would touch
every caller of `core.security.create_access_token`/`decode_access_token`
for a single phase, and a claim baked into a 15-minute-old access token
can't reflect a role change made 30 seconds ago anyway. Every
organization-scoped route instead takes `organization_id` as a path
parameter, and `require_membership` does one real, cheap
`SqliteMembershipStore.get()` lookup per request -- the same per-request-
store-lookup cost every other route in this API already pays, always
current, never stale. A non-member gets a `404` (not `403`) for any
organization-scoped route -- the same "don't reveal whether the resource
exists to a caller who can't see it" discipline Phase 58 already applies
to cross-user notification access.

### Invitations: real hashed tokens, real delivery reuse where the architecture allows it

`career_agent/invitations.py` (top-level, same "composition root, not a
layer" reasoning that already placed `scheduler.py`/`organizations.py`
there) mirrors `SqlitePasswordResetTokenStore`'s own "store a hash, never
the raw token" discipline exactly. **Delivery never duplicates email
logic**: it always calls `scheduler.build_email_sender(settings)` for the
real SMTP transport Phase 58 built. When the invited email already has an
account, the *full* `NotificationEngine`/`NotificationDispatcher` path
runs -- in-app notification plus the account's own email/webhook
preferences, exactly like every other real trigger event
(`category="invitation_received"`, a category ADR-0077 explicitly
deferred for "no invitation system exists" -- now real, added to the
closed `NotificationCategory` set). When the invited email has no
account yet, there is no `user_id` an in-app row could ever belong to, so
delivery falls back to a direct `EmailSender.send()` call -- named here
as exactly that limitation, not silently skipped. Either path is wrapped
in a broad exception catch: a delivery failure never blocks the
invitation itself from existing ("notify, never gate," ADR-0005).
Accepting is the one flat, non-organization-scoped route
(`POST /team/invite/accept`) -- the caller isn't a member of the target
organization *yet*; accepting is how they become one.

### Billing: a real port+adapter, no external payment call

`integrations/billing.py`'s `BillingService` protocol + `FakeBillingProvider`
is the exact same port+adapter shape every other integration in this
project already uses (`EmailSender`/`SmtpEmailSender`,
`WebhookSender`/`HttpClient`) -- swapping in a real Stripe-backed provider
later means writing one new class against this protocol, not touching any
call site. `career_agent/billing.py` composes it with
`SqliteSubscriptionStore`/`SqliteUsageCounterStore` (three fixed plans:
free/pro/enterprise). The one place the stub's behavior genuinely differs
from a real integration, named directly: a real provider activates a plan
change only after a webhook confirms payment; this stub has no payment to
wait for, so `POST /billing/{id}/checkout` activates immediately. Seat
limits are **actually enforced**, not just displayed -- `invite_member`
calls `billing.seat_limit_exceeded` before creating an invitation and
returns `402 Payment Required` past the plan's `max_seats`, so "upgrade
to invite more" is a real constraint a test exercises, not a number on a
pricing page no code reads.

### Audit log: append-only, best-effort, never gates the real action

`storage/audit_store.py::SqliteAuditLogStore` is append-only (never
updated, the same discipline `SqliteDeliveryAttemptStore` already holds
itself to). `api/audit.py::record_audit` is the one place every mutating
organization route calls into -- user/organization/action/result/IP/
timestamp -- and swallows its own storage errors so a failed audit write
can never fail the real action it's describing (the same "notify, never
gate" precedent, applied to observability instead of delivery).

### Platform admin: `require_admin`'s first real caller

`api/routers/admin.py` is gated by `api.security.require_admin` --
`User.role == "admin"`, the account-level flag Phase 56 declared
("forward compatibility... nothing in this phase actually grants a route
admin-only access yet") and left genuinely unused until now. Deliberately
minimal: list every organization on the platform, list any organization's
members -- real, useful, ops-facing visibility, not a full impersonation/
"act as any user" capability the brief never asked for.

### API surface

Two new categories of router, split by whether they mutate anything.
**GET-only** (`roles.py`, `admin.py`, `audit_log.py`) live under `/api/`
and join the existing `_READ_ONLY_ROUTERS` group, getting the existing
structural GET-only proof for free. **Mutation-capable**
(`organizations.py`, `team.py`, `billing.py`) join `/auth/`, `/user/`,
`/coach/`, `/notifications/`, `/notification-settings` as the API's only
write-capable exceptions, each proven both permission-gated and
organization-isolated by dedicated tests -- never bypassing or weakening
the existing `test_dashboard_data_routes_are_get_only` /
`test_auth_and_user_are_the_only_write_capable_routers` structural tests,
only extending their allowlists.

### Frontend: organization_id as a route param, not a new global context

No new "current organization" React context. Team/Billing/Audit Log
pages are reached via `/organizations/:organizationId/{team,billing,audit}`
-- the `OrganizationsPage` (a real org switcher/list/create page) links
into each org's own pages, matching the RBAC design's own
`organization_id`-in-the-path convention rather than introducing global
client state that could drift from the URL. `AcceptInvitePage` reads
`?token=` from the URL and drives the real accept flow. The sidebar's new
"Organization" section and a conditionally-rendered "Platform Admin" link
(gated client-side on `user.role === "admin"`, mirroring the same check
the backend already enforces -- a UX nicety, not the actual security
boundary, which stays server-side).

## What this phase explicitly does not do

- **No real Stripe integration.** `FakeBillingProvider` is the entire
  billing surface; no external payment call exists anywhere in this
  codebase. Named directly in `integrations/billing.py`'s own docstring.
- **No SSO/SAML/OIDC.** Authentication remains exactly Phase 56's
  email+password JWT model, unchanged.
- **No SCIM provisioning.** Team membership is managed entirely through
  this phase's own invite/accept/remove flow.
- **No custom, per-organization roles.** Five fixed roles with a fixed
  permission matrix (`domain/roles.py::ROLE_PERMISSIONS`) -- no
  admin-configurable role editor.
- **No retrofit of `organization_id` onto the nine pre-existing personal-
  resource tables** (résumé variants, application sessions, review
  sessions, submission results, notifications, notification preferences,
  delivery attempts, webhook subscriptions, user preferences). Named
  above under "Context" -- doing so would mean rewriting every existing
  store/router this phase's own brief says not to rewrite. Each user's
  existing personal data remains exactly as user_id-scoped as it already
  was; organization membership governs who can manage the *organization*
  (team, billing, audit, settings), not who can see whose résumé.
- **No CLI organization-awareness.** `career-agent prepare`/`review`/
  `submit` remain the single fixed local-operator account they have been
  since Phase 56 -- no login flow, no org selection. The dashboard is the
  multi-tenant surface; the CLI stays the self-hosted power-user tool
  ADR-0000 always described, even after its non-goal amendment.
- **No horizontally-scalable rate limiting.** `api/rate_limit.py`'s
  in-memory, per-process limiter is unchanged -- ADR-0074 already named
  Redis as the eventual answer for a real multi-instance deployment; nothing
  here required it, so nothing here adds it.
- **No usage-based billing metrics beyond live seat count.**
  `SqliteUsageCounterStore` exists and is real, but nothing increments it
  yet (no metered feature exists to track); `seats` is the one metric
  computed live because it needs no separate increment call. Named
  directly in `api/routers/billing.py`'s own docstring.

## Consequences

- Backend: `domain/{organization,team,roles,audit,billing}.py`;
  `storage/{organization_store,team_store,audit_store,billing_store}.py`;
  `career_agent/{organizations,invitations,billing}.py` (top-level,
  composition-root-adjacent, mirroring `scheduler.py`'s own placement);
  `integrations/billing.py`; `api/rbac.py`, `api/audit.py`; `api/routers/
  {organizations,team,roles,admin,audit_log,billing}.py`; `api/app.py`
  gains three new write-capable routers and three new read-only ones,
  plus the startup organization-migration call; `api/routers/auth.py`'s
  `register` gains personal-organization creation. `Settings` gains
  `frontend_base_url` (for building an absolute accept-invitation link in
  email). `domain/notification.py`'s `NotificationCategory` gains
  `invitation_received`/`invitation_accepted`. 116 new backend tests
  (1349 total); full suite, ruff, and all import-linter contracts green.
- Frontend: `services/{organizationsApi,teamApi,billingApi,auditApi,
  adminApi}.ts`; `hooks/{useOrganizations,useTeam,useBilling,useAuditLog,
  useAdmin}.ts`; `pages/{OrganizationsPage,TeamPage,BillingPage,
  AuditLogPage,AcceptInvitePage,AdminPage}.tsx`; new routes in `App.tsx`;
  a new "Organization" sidebar section plus a conditionally-rendered
  "Platform Admin" link in `layouts/Sidebar.tsx`. 19 new frontend tests
  (68 total); `tsc`/`oxlint`/`vite build` green.
- Zero changes to `SubmissionEngine`, `ReviewEngine`, `NotificationEngine`,
  the résumé-tailoring pipeline, the Career Coach, the scheduler's job
  logic, or the JWT/refresh-token authentication model. The nine
  pre-existing personal-resource tables and their stores are byte-for-
  byte unchanged.
- `docs/adr/0000-project-philosophy.md` amended (Status line + "Future
  revisit criteria" note only -- original decision text unchanged) to
  point here for its multi-tenancy non-goal.

## Future revisit criteria

- If real payment processing is ever needed, implement a
  `BillingService` backed by Stripe (or similar) against the exact
  protocol `integrations/billing.py` already defines -- no call-site
  changes required elsewhere.
- If per-organization custom roles are ever requested, that is a genuine
  data-model change (roles/permissions become organization-owned rows,
  not a fixed in-code mapping) -- a dedicated phase, not a bolt-on.
- If any of the nine pre-existing personal-resource tables ever need
  real organization-wide visibility (e.g. "an org admin reviews résumés
  prepared by any member"), that is the retrofit named as deferred above
  -- revisit this ADR's scoping reasoning at that point, with its own
  audit of exactly which stores/routers must change.
- If the CLI is ever given its own login/organization awareness, that is
  a architecturally significant change to a tool that has been
  single-operator since inception -- requires its own explicit
  authorization, the same standard this ADR's own multi-tenancy question
  required.
- If this deployment ever needs true horizontal scaling, the in-memory
  rate limiter (and the in-process APScheduler, ADR-0077) both need a
  real distributed replacement -- already named in ADR-0074/ADR-0077,
  unchanged by this phase.
