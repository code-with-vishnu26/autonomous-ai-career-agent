# ADR-0089: Web Résumé Upload + AI Analysis + Signed Résumé-PDF Excel Links

- **Status:** Accepted
- **Date:** 2026-07-14
- **References:** [ADR-0052](0052-evidence-grounded-cv-ingestion.md) (the
  fail-closed CV-ingestion/promotion boundary reused unmodified here),
  [ADR-0082](0082-per-user-master-profile-onboarding.md) (named "CV upload
  ... explicitly deferred to a dedicated future phase" -- this is that
  phase), [ADR-0087](0087-enriched-excel-company-research.md) (named "a
  dedicated résumé/cover-letter download endpoint is named follow-up
  work" -- this delivers it, plus the Company LinkedIn column),
  [ADR-0074](0074-authentication-and-multi-user-platform.md) (the access/
  refresh JWT pair this adds a third, purpose-scoped token kind alongside)

## Context

The owner asked for two things: (1) when the AI asks a user for their
details, it should also let them upload their résumé, analyze it, and use
those facts for onboarding and downstream features; (2) the applications
Excel should carry the company webpage link, "working employee details,"
LinkedIn, and a clickable PDF link to whichever résumé the AI actually
submitted, with all of it accessible to the user.

On "working employee details": this exact question was already asked and
settled earlier in this project (ADR-0087's Context) -- the owner chose
**public company channels only**, not named individuals, upholding
ADR-0036's no-scraping-of-people invariant. This phase honors that
decision rather than reopening it: "employee details" here means the
company's own public channels (careers page, company LinkedIn page), never
a person's name or contact info.

Two things this phase depends on were already true, found on inspection
rather than assumed:

- ADR-0052 built a complete, exhaustively-verified fail-closed pipeline for
  turning résumé text into `MasterProfile` facts -- parse → propose
  `UNVERIFIED` facts with evidence spans → user confirms/rejects → `promote()`
  writes only admissible, confirmed facts. It was CLI/file-based
  (`import-cv`/`promote-cv` against paths on disk) but the underlying
  `domain/ingestion.py` boundary has no I/O assumption baked in -- only
  `storage/cv_ingest.py`'s two entry points (`read_document`/
  `ingest_document`) took a `Path`. A web upload needed the identical
  trust semantics against `UploadFile` bytes instead, not a second,
  parallel implementation.
- ADR-0052 explicitly deferred PDF support ("no declared PDF reader is
  safe to rely on"), naming DOCX/TXT/MD export as the workaround. That
  workaround is fine for a terminal user willing to convert a file; it is
  not fine for a web user whose résumé, in the overwhelming majority of
  cases, already exists as a PDF and who has no reason to own a DOCX
  copy. Checking dependencies actually resolved in this environment found
  `pypdf` already present -- as an *undeclared transitive* of
  `browser-use`. Relying on an undeclared transitive is exactly the
  "unsafe to rely on" ADR-0052 flagged; declaring it directly at the
  version already resolved turns a named gap into a real, tested
  capability without a new supply-chain surface.
- No `ResumeVariant` artifact path (DOCX/PDF) is persisted anywhere --
  `ResumeTailoringResult.artifacts` (`agents/resume/pipeline.py`) is
  transient/in-memory only. So "which résumé the AI submitted, as a PDF
  link" cannot mean "link to a stored file"; it has to mean "regenerate
  the real thing on demand," or the export would need an invasive schema
  change (persisting artifact paths that could later point at a deleted
  file).
- An Excel hyperlink is opened later, from inside Excel, with **no
  browser session** -- the in-memory access token that authenticates every
  other API call is not available to it. This is the same reason ADR-0087
  left the résumé out of the export in the first place.

## Decision

### Résumé upload, reusing ADR-0052's boundary unmodified

`storage/cv_ingest.py`'s `read_document(path)`/`ingest_document(path)`
become thin wrappers over two new bytes-based entry points --
`read_document_bytes(filename, raw_bytes)` / `ingest_document_bytes(filename,
raw_bytes, *, source_path=None)`. The CLI (disk) and the web (`UploadFile`)
now share one parser with zero duplicated logic; nothing in
`domain/ingestion.py` (`FactProposal`/`TrustState`/`promote`/
`detect_conflicts`/`confirmation_digest`) changes at all. A new
`_extract_pdf_text` uses the now-declared `pypdf`; a scanned/image PDF
with no text layer yields an empty string, which proposes no facts --
never an error (a résumé with no extractable facts is not a malformed
document).

`api/routers/cv_import.py` is the two-step HTTP analogue of
`import-cv`/`promote-cv`:

- `POST /user/master-profile/import` (multipart `UploadFile`) parses the
  upload via `ingest_document_bytes`, caches the resulting
  `IngestionDraft` + normalized document text server-side keyed by an
  opaque token (module-level `_pending` dict, the same in-memory-pending
  pattern `prepare_actions.py`/`submission_actions.py` already use, scoped
  to the uploading user, pruned after an hour), and returns every proposed
  fact -- field path, proposed value, an evidence snippet, conflict ids --
  **without touching the profile**. The client never holds or replays the
  document; only a token.
- `POST /user/master-profile/import/{token}/confirm` takes the caller's
  per-proposal confirm/reject decisions, builds the trust-state-updated
  proposals, and calls `apply_confirmed_promotions` -- the *exact* Phase 26
  function, unmodified -- against the caller's existing stored
  `MasterProfile` (or an empty starting shape if this is their first
  profile). A proposal the client never mentions stays `UNVERIFIED` and is
  never promoted (verified by test). Saves only when the resulting profile
  has both required basics (`name`, `email`); otherwise reports which are
  still missing so the caller can keep filling the onboarding wizard by
  hand for the rest. Confirming a fact that conflicts with a *different*
  existing trusted value yields `REQUIRES_RESOLUTION`, never a silent
  overwrite -- `promote()`'s existing behavior, unchanged, re-verified by
  a new test against this endpoint specifically.

This is "the AI analyzes your résumé and uses it" without weakening the
one guarantee this whole subsystem exists to protect: no résumé text ever
becomes a trusted profile fact, and therefore no downstream tailored
résumé claim, without an explicit human confirmation.

### Signed résumé-PDF download link (the Excel "which résumé" answer)

A **third JWT kind**, alongside the existing access/refresh pair
(`core/security.py`): `create_resume_download_token`/
`decode_resume_download_token`, carrying `purpose="resume_download"` +
`variant_id`, deliberately shaped differently from an access token (no
`role` claim) so each decoder rejects the other's token even though both
are HS256-signed with the same secret -- the same confusion-prevention
discipline `confirmation_digest` already applies to content digests,
applied here to token kinds. A test proves the rejection is mutual.

`GET /export/resume/{variant_id}.pdf?token=...` is deliberately **not**
session-authenticated (no `get_current_user` dependency) -- the token in
the URL *is* the authorization, the same presigned-URL model any
object-storage download link uses, because this link is opened outside
the app entirely. It decodes the token, checks the token's
`resume_variant_id` matches the path's `variant_id`, checks the token's
`user_id` actually owns that variant (`resume_variant_store.by_user(...)`),
then **renders fresh** from the stored `ResumeVariant.content` +
the owner's `MasterProfile` using the exact same `render_resume_docx`/
`convert_to_pdf` functions `prepare`/`submit` already call -- so what
downloads is always the real tailored résumé, never a stale or
since-deleted cached file, and no schema change was needed to persist an
artifact path. Returns a real `503` (never a bare 500) if this server has
no PDF converter installed, matching ADR-0080's "the capability may not
exist here" precedent -- it is a named environment constraint, not a bug.

`_enriched_application_rows` (`api/routers/export.py`) now mints one such
token per row that has a `resume_variant_id`, and builds an **absolute**
URL from it -- a new `api_base_url` setting (mirroring the existing
`frontend_base_url`, which exists for the identical reason: an
invitation email link also has no browser origin to resolve a relative
path against). `storage/excel.py` gained a `Résumé (PDF)` hyperlink
column (link expiry 90 days -- long enough for a job search, short enough
that a leaked spreadsheet doesn't grant access forever) alongside a
`Company LinkedIn` column, filled from a new `linkedin_url` field on
`domain/company_research.py`'s `CompanyResearch`. Detection
(`agents/research/company_research.py`) requires the literal substring
`linkedin.com/company/` -- never `/in/` (a person) -- so this stays a
public company channel, the same line `careers_url` already draws, and the
same boundary `CompanyResearch`'s own docstring commits to (no personal
data about individuals, ever).

### Production routing fix (found while wiring the above)

`deploy/nginx/edge.conf`'s regex claimed to mirror
`frontend/vite.config.ts`'s dev-proxy prefix list but had drifted --
`/export` (added ADR-0083), `/discover`/`/prepare`/`/reviews`/
`/submissions` (ADR-0081), `/team`/`/billing` (ADR-0078),
`/notifications`/`/notification-settings` (ADR-0077) were all missing, so
none of those routes reached the backend through the production edge
proxy at all. This was a pre-existing gap, not introduced here, but it is
a hard blocker for this phase's own `/export/resume/*.pdf` link working
in production, so it is fixed in the same commit: the regex now lists
every prefix `vite.config.ts`'s `API_PREFIXES` does. Left as a named,
not-fixed-here gap: `/coach`, `/notifications`, `/notification-settings`,
`/organizations` are *also* client-side routes, so a production refresh on
one of those pages still hits the backend's raw JSON instead of the SPA --
the same problem `vite.config.ts`'s `Accept: text/html` bypass solves for
local dev. A correct nginx-side fix needs a variable `proxy_pass` + an
explicit `resolver` (Docker Compose's embedded DNS) and is out of scope
for this phase.

## Consequences

- A user can upload a résumé (PDF, DOCX, TXT, or MD) during or after
  onboarding, review exactly what the AI extracted with the evidence it
  found for each fact, and decide field-by-field what becomes part of
  their trusted profile -- ADR-0052's "no unverified fact silently becomes
  evidence" guarantee is provably intact (reused code, new tests against
  the HTTP boundary specifically). This is a real, shipped UI, not just an
  API: `ResumeImportPanel` sits on the onboarding wizard's Welcome step,
  and a successful confirm writes into the same query cache the rest of
  the wizard's form reads from, so confirmed facts pre-fill the remaining
  steps immediately -- verified end to end with a real headless-Chromium
  run (register, upload, confirm two proposals, land on Personal Details
  already showing the confirmed name and email), not only component
  tests.
- PDF is no longer a deferred format -- ADR-0052's own named limitation is
  resolved, not worked around, for both the CLI and the web.
- The applications Excel now answers "which résumé did the AI submit" with
  a real, clickable, always-current PDF link, and adds the company's
  public LinkedIn page next to the careers page ADR-0087 already added.
  "Working employee details" is deliberately *not* personal data about
  named individuals -- the owner's own earlier decision, upheld again here,
  not silently reinterpreted.
- A stale or previously-cleaned-up artifact can never be linked to, because
  nothing is ever linked to a file path -- every download re-renders from
  the same source of truth `prepare`/`submit` use.
- `pypdf` and `python-multipart` are now real, declared dependencies
  (the latter web-extra only, since it is FastAPI's own requirement for
  `UploadFile` and nothing else in this project uses multipart forms).
- The production edge-proxy routing gap silently affecting `/export`,
  `/discover`, `/prepare`, `/reviews`, `/submissions`, `/team`, `/billing`,
  `/notifications`, `/notification-settings` is fixed; the separate
  SPA-route-collision gap on four prefixes is named, not fixed, follow-up.
- The CLI's `import-cv`/`promote-cv`/`profile.json` workflow is completely
  unchanged -- both entry points now share one parser, but each keeps its
  own store, its own trigger, and its own test suite.

## Limitations (honest)

- OCR is still not supported -- a scanned/image PDF with no text layer
  proposes zero facts (never an error). Named in ADR-0052, still true here.
- Work/education entries are still not auto-proposed from a résumé (parse
  quality too low to be worth the fabrication risk) -- unchanged from
  ADR-0052; only the high-value contact/skill fields are.
- The résumé-download token cannot be revoked individually before its
  90-day expiry (no token-revocation list exists for any token kind in
  this project yet, including access/refresh) -- consistent with the
  existing access-token model, not a new gap this phase introduces.
