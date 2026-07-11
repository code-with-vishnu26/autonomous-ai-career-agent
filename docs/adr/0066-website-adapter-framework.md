# ADR-0066: Website Adapter Framework (search delegates to existing sources, browser hooks are new)

- **Status:** Accepted
- **Date:** 2026-07-11
- **References:** [ADR-0015](0015-web-search-classification.md)/
  [ADR-0019](0019-ats-kind-resolution-and-tier-fallback.md)
  (`resolve_ats_kind`), [ADR-0028](0028-browser-tier-dispatch-and-unsupported-field-refusal.md)/
  [ADR-0029](0029-per-filler-challenge-and-submit-selectors.md)/
  [ADR-0035](0035-real-lever-form-filler.md)
  (`FormFiller` — verified vs. stubbed selectors), [ADR-0065](0065-browser-automation-foundation.md)
  (Phase 47, `BrowserManager`/`SessionManager`/`TabManager`)

## Context

Phase 48 asks for a "Website Adapter Framework": a common interface over
Greenhouse/Lever/Ashby/Workday/RemoteOK/Remotive/Arbeitnow/TheMuse, so a
future caller never switches on provider names, with `search()`,
`open_job()`, `extract_job()`, `detect_login()`, and capability flags
(`supports_resume_upload`, etc.) per adapter. Explicitly no form-filling,
no login automation, no submission this phase.

The mandatory repository-reality audit found this is, again, not
greenfield. **Six of the seven named providers already have a real,
working, tested, API-based
:class:`~career_agent.core.interfaces.OpportunitySource`**
(`plugins/sources/{greenhouse,lever,ashby}.py`,
`plugins/sources/job_boards.py`'s `Arbeitnow`/`TheMuse`/`Remotive`/
`RemoteOk` sources) — all already wired into `career-agent discover`.
`domain/ats_urls.py::resolve_ats_kind` already does exactly the
deterministic, no-AI provider detection the brief asks for, for
Greenhouse/Lever/Ashby. `agents/apply/form_fillers.py` already establishes
this project's precedent for *application-form* capability claims:
`GreenhouseFormFiller` and `LeverFormFiller` are real, verified against a
live posting's DOM; `AshbyFormFiller` is an **explicit stub** because no
live posting's selectors were ever verified — never a guess. Only
**Workday has zero prior art anywhere** in this codebase.

## Decision

**`search()` delegates to the existing source; only the browser-facing
half is new.** Each of the six providers with a real source gets a thin
`WebsiteAdapter` wrapping it — `search()` calls the existing
`fetch(since)`, unchanged, faster and more reliable than browser scraping.
Workday's adapter is an honest stub (`search()` raises
`FeatureUnavailableError`, never a silent empty result), matching
`AshbyFormFiller`'s own precedent.

### No new canonical job model

The brief asks for a new `JobPosting` structure. **Decision: reuse
`domain.models.Opportunity`, do not invent a parallel model.**
`Opportunity` already is the canonical normalized job-posting
representation (id/company/title/location/remote/description/source/
provenance), deeply embedded through Discover/Decide/Apply and already
what every `OpportunitySource` (including the six this phase wraps)
returns. A second, parallel `JobPosting` model would duplicate
`Opportunity`'s fields and create two subtly-different representations of
the same thing — every project convention so far (`load_job_preferences`
vs. `MasterProfile`, `test_purity.py`'s zero-duplication discipline)
argues against that. Capability flags
(`supports_resume_upload`/`supports_cover_letter_upload`/
`supports_easy_apply`) are properties of the *platform*, not of a specific
job posting, so they belong on the adapter class (mirroring
`FormFiller.known_field_selectors` and
`~career_agent.core.interfaces.ProviderCapabilities`'s existing "declared
on the interface" pattern), never on `Opportunity` itself.

### Capabilities are evidence, not defaults

Every `AdapterCapabilities` value is grounded in existing verified
evidence, not assumption:

| Provider | `resume_upload` | Evidence |
|---|---|---|
| Greenhouse | `False` | `GreenhouseFormFiller`: `#resume_text` is a manual **text** field |
| Lever | `True` | `LeverFormFiller`: `[name='resume']` is a **required file upload** (`set_input_files`) |
| Ashby | `False` (unverified) | `AshbyFormFiller` is an explicit stub — no live posting inspected |
| Workday, RemoteOK, Remotive, Arbeitnow, TheMuse | `False` (unverified) | No `FormFiller` exists for any of these; aggregators typically link out to the employer's own apply page |

No cover-letter field or "easy apply" flow has been verified for *any*
platform in this codebase, so those two flags are `False` everywhere.

### No vendor-specific DOM selector guessing for job-posting content

Neither this codebase nor its `FormFiller` history has ever inspected a
live posting's *content* DOM (title/description) — only the *application
form* DOM, and only for Greenhouse/Lever. `extract_job()` (a fallback for
when only a URL is known, not the primary discovery path) therefore uses
**only universal, standards-based signals**: Open Graph meta tags
(`og:title`/`og:description` — a documented cross-site convention, not a
vendor-specific internal detail) and the page's plain `<title>` element as
a title-only fallback. Never a guessed CSS class or `id`, the same
discipline that kept `LeverFormFiller`/`AshbyFormFiller` honest.

### Placement and reuse

`integrations/adapters/` (alongside Phase 47's `integrations/browser/` —
both are "integration with an external system," this project's existing
unlayered I/O category). `open_job`/`extract_job`/`detect_login` are
identical across every adapter (only `supports()`/`search()`/`provider`/
`capabilities` differ), so a `BrowserAdapterMixin` in `base.py` supplies
them once — `open_job` calls Phase 47's `TabManager.open_tab`;
`detect_login` calls Phase 47's `SessionManager.is_logged_in` (the caller
supplies `indicator_selector`; no adapter hardcodes one — no verified
"logged in" selector exists for any platform either). `prepare_application`
always raises `FeatureUnavailableError` this phase — declared on the
interface now so a future phase extends rather than bolts it on, the same
non-goal discipline as everywhere else in this framework.

### Provider detection

`AdapterRegistry.find(url)` tries `resolve_ats_kind` first (reused
unchanged for Greenhouse/Lever/Ashby), then a new, package-local hostname
table for the four job boards plus Workday's real, publicly documented
multi-tenant hosting domain (`myworkdayjobs.com`) — pure deterministic
string matching, no AI, no network fetch, the exact discipline the brief
asked for. `domain/ats_urls.py` itself is untouched (its existing
ADR-0015/0019 contract and two existing call sites are unaffected).

### Discovery integration

The brief asks for "provider metadata" attached to discovered
opportunities. **Decision: derive it on demand via `detect_provider(url)`,
never add a new persisted field to `Opportunity`.** The provider is always
recoverable from `source_url`; storing a second, potentially-drifting copy
of the same fact would violate the same "derive, don't duplicate"
principle used everywhere else in this codebase.

## What this phase explicitly does not do

No form-filling, no login automation, no credential storage, no typing
into forms, no resume/cover-letter uploads, no AI, no planner, no CLI
command, no wiring into `career-agent discover`'s composition root (that
requires new `Settings` fields for board/company tokens the existing
`build_discovery_sources` doesn't have either — a deliberate, separate,
future decision, not an oversight). No change to `BrowserApplicator`,
`FormFiller`, or the execution-safety boundary.

## Consequences

- New `src/career_agent/integrations/adapters/` package: `base.py`,
  `registry.py`, and one module per provider (`greenhouse.py`, `lever.py`,
  `ashby.py`, `workday.py`, `remoteok.py`, `remotive.py`, `arbeitnow.py`,
  `themuse.py`).
- 45 new tests: fixture-driven delegation tests (reusing the exact
  fixtures each wrapped `OpportunitySource`'s own tests already use),
  registry/detection tests, capability-evidence tests, and real-Chromium
  tests for the browser-facing mixin methods (same discipline as Phase
  47's tests — skip automatically with no local Chromium build).
- No new dependency, no version bump, no `Opportunity`/`ats_urls.py`
  change.

## Future revisit criteria

Phase 49 (AI Planner) and beyond are the first real consumers of
`search()`/`AdapterRegistry`. When `career-agent discover` is wired to use
this framework directly (rather than `build_discovery_sources`'s current
independent wiring), revisit whether the two composition paths should
merge — deliberately not done in this phase to keep the diff additive.
