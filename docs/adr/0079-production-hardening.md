# ADR-0079: Production Hardening (Observability, CSP, Dependency/Secret Scanning)

- **Status:** Accepted
- **Date:** 2026-07-12
- **References:** [ADR-0076](0076-production-deployment-and-infrastructure.md)
  (structured JSON logging, request logging, security headers at the nginx
  edge -- this phase's actual starting point), [ADR-0074](0074-authentication-and-multi-user-platform.md)
  (the rate limiting and CSRF decisions this phase re-examines and
  reaffirms rather than duplicates), [ADR-0078](0078-saas-multi-tenant-platform.md)
  (the most recent feature phase; this one is deliberately not another
  feature phase)

## Context

The roadmap (Phases 1-60) is feature-complete: CLI pipeline, Web Dashboard,
authentication, Career Coach, notifications, production Docker deployment,
and multi-tenant Organizations/RBAC. Continuing to add features from here
would work against this project's own stated philosophy
([ADR-0000](0000-project-philosophy.md)) of shipping what's real rather
than what's next on a list. The owner asked for the next phase to focus on
**production hardening** instead: observability, error handling, security
headers, and CI-native dependency/secret scanning.

**A repository-reality audit (mandatory before any implementation) found:**

- **Logging** (ADR-0076) already has structured JSON logging and one
  request-log line per request. **Missing**: no request-correlation ID --
  nothing ties a request's log lines together, or ties a background job
  triggered by a request back to it.
- **Error handling**: `api/app.py` had no global exception handler.
  Individual `except Exception` sites are already deliberate and
  documented (fail-open/fail-closed per call site, each with a `# noqa:
  BLE001` and an inline reason) -- not a bug pattern, so left alone. An
  unhandled exception at the route layer, however, fell through to
  FastAPI's bare default 500 with no correlation ID and no guaranteed log
  line through this project's own structured logger.
- **Security headers**: `X-Content-Type-Options`, `X-Frame-Options`, and
  `Referrer-Policy` already exist at the nginx edge and frontend containers
  (ADR-0076). **Missing**: no Content-Security-Policy anywhere, at either
  layer.
- **Rate limiting** (ADR-0074): a documented, intentional,
  process-local-only `InMemoryRateLimiter`, applied to `auth` routes only.
  Still correct for this phase's scope -- broadening it to every route is
  a larger, separate decision this phase does not make; see "Deferred"
  below.
- **CSRF** (ADR-0074's own `auth.py` docstring): a deliberate decision
  already made and reasoned about (`SameSite=Lax` cookie, no CSRF token,
  explicit rationale inline) -- reaffirmed, not reopened.
- **Dependency/secret scanning**: CI ran `ruff` and `pytest` only. No
  `pip-audit`, `npm audit`, secret scanner, or `dependabot.yml` existed.
- **Business-logic layering**: a spot check found the CLI, scheduler, and
  API routers already call into the same domain/service functions (no
  inline reimplementation found in the files checked) -- no action needed
  here; a full router-by-router audit was out of scope for this pass.

## Decision

Four real, scoped changes -- no new feature surface, no rewrite of
anything already working.

### 1. Request-correlation IDs

`core/request_context.py` (new): one `contextvars.ContextVar`, framework-
agnostic (no FastAPI import -- this project's layers contract keeps `core`
free of an `api`-layer dependency; `tests/test_architecture.py` enforces
it). `api/middleware.py`'s new `request_id_middleware` reads an incoming
`X-Request-ID` header if the caller (or a future edge proxy) already set
one, otherwise generates a UUID4; sets it on both the contextvar (for
logging, via a new `RequestIdLogFilter` applied once at the root logger in
`configure_logging`) and `request.state.request_id` (for the exception
handler below); always returns it in the response's `X-Request-ID` header.

Registered as the **outermost** app middleware (before `log_requests`) so
every request-scoped log line -- including `log_requests`' own -- already
carries the ID.

**Why both a contextvar and `request.state`, not just one:** discovered by
testing, not assumed. Starlette treats a handler registered for the bare
`Exception` type specially -- it becomes `ServerErrorMiddleware`'s
`error_handler`, which sits **outside** every `app.middleware("http")`
callback (`build_middleware_stack`'s `if key in (500, Exception):` branch).
By the time an exception has propagated through `request_id_middleware`'s
`try/finally`, the contextvar has already been reset back to `""` -- but
the same `Request` object's `.state` survives regardless of how the
exception unwound. Verified with a real `TestClient` call before and after
the fix (`tests/api/test_middleware.py`).

### 2. Global exception handler

`api/app.py::_handle_unexpected_error`, registered via
`app.add_exception_handler(Exception, ...)`. Only affects genuinely
unhandled exceptions -- Starlette's `ExceptionMiddleware` still matches
`HTTPException` (and any other more-specific registered handler) first, so
every existing route's 401/403/404/422 behavior is unchanged (verified by
`test_existing_http_exceptions_are_unaffected`). Logs the full traceback
via this project's own structured `logging.exception(...)` (so it lands in
JSON when `JSON_LOGS=true`, with the request ID attached) and returns
`{"detail": "Internal server error", "request_id": "..."}` -- never
`str(exc)` or any traceback fragment, which is exactly the internal detail
(a file path, a SQL fragment, a stack frame) this exists to keep off the
wire.

### 3. Content-Security-Policy

Added to both `deploy/nginx/edge.conf` and `deploy/nginx/frontend.conf`
(the same defense-in-depth duplication already established there for the
other three headers): `default-src 'self'; script-src 'self'; style-src
'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:;
connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action
'self'`.

`script-src` has no `'unsafe-inline'`/`'unsafe-eval'` -- the SPA build has
no inline `<script>`, only its own hashed module bundle. `style-src` keeps
`'unsafe-inline'` as a **documented, deliberate loosening**: React and
Recharts (this dashboard's charting library) set inline `style="..."`
attributes at runtime, and there is no build-time nonce/hash mechanism
wired today to avoid it. Tightening that further is future work, not
silently pretended-away here.

### 4. CI-native dependency and secret scanning

- **`pip-audit`** (backend `verify` job, both OS legs): real vulnerability
  scan against the installed environment. **20 known CVEs across
  `aiohttp==3.13.4`/`pypdf==6.10.2` are explicitly `--ignore-vuln`'d, named
  individually in the workflow** -- both are *exact-pinned* transitive
  dependencies of `browser-use` (the Submission Engine's real browser
  automation library, not something this project chose to add). Verified
  the latest available `browser-use` release (0.13.4, checked 2026-07-12)
  still pins the identical vulnerable versions -- there is no newer,
  compatible version to move to today. This is a genuine upstream
  constraint, not a shortcut: forking or monkey-patching a third-party
  browser-automation dependency to unpin two transitive libraries is a far
  bigger, riskier undertaking than a hardening phase should take
  unilaterally. Named here and in CI, not silently skipped; revisit when
  `browser-use` relaxes or bumps its own pins. `pip` itself was upgraded
  (fixes its own 5 CVEs for real, no ignore needed).
- **`npm audit`** (frontend `verify-frontend` job): genuinely clean today
  (0 vulnerabilities) -- added as a real, unconditional gate.
- **`detect-secrets`** + `.secrets.baseline` (new, committed) +
  `scripts/check_secrets_baseline.py` (new): re-scans on every CI run and
  fails if the scan no longer matches the committed baseline. The initial
  scan found 29 files with `Secret Keyword`-heuristic matches -- all
  verified by hand to be placeholder/test-fixture values (`docker.env`'s
  own "safe to commit" comment, test JWT secrets like
  `"unit-test-secret-not-for-real-use"`, promptfoo config comments
  mentioning "key"), never a real credential. Two real bugs found and
  fixed while building this, both by testing the actual tool rather than
  assuming it would work: (1) `detect-secrets` enumerates scan targets via
  `git ls-files`, not a raw filesystem walk -- a naive re-scan in a
  directory with no `.git` silently finds nothing; (2) the baseline file
  itself was being scanned, so its own recorded secret-hashes looked like
  fresh high-entropy findings, snowballing on every regeneration -- fixed
  by excluding `.secrets.baseline` from its own scan. The check also
  strips `generated_at` (changes every run) and the `is_baseline_file`
  filter's absolute `--baseline` path (differs between a contributor's
  machine and CI's runner) before comparing, or CI would fail on every
  single run regardless of whether a real secret changed.

Both new CI tools live in their own `security` extra
(`pip install -e ".[dev,security]"`), not folded into `dev` -- neither
`verify-frontend` nor `docker` needs them, and `detect-secrets` shelling
out to `git` is an extra runtime assumption worth keeping opt-in.

## Consequences

- Every API response (success or error) now carries `X-Request-ID`; every
  structured log line carries the same ID when produced during a request.
  Nothing about existing routes' behavior, status codes, or response
  bodies changed for the success/expected-error paths.
- An unhandled exception now returns a safe, consistent JSON body instead
  of FastAPI's bare default, and is guaranteed to reach this project's own
  structured logger with a traceback and correlation ID.
- The dashboard's CSP is real and enforced at both nginx layers; a future
  XSS attempting to load an external script or exfiltrate via `fetch` to a
  non-`'self'` origin is blocked by the browser itself, not just by
  application-level escaping.
- CI now fails closed on a new *fixable* dependency vulnerability, a new
  `npm` vulnerability, or a new potential secret -- with the two currently
  unfixable `browser-use`-pinned CVE sets named explicitly rather than
  either silently ignored (a blanket `continue-on-error`, which this
  project's CI has never used and still doesn't) or left to permanently
  block CI on a constraint nobody here can fix today.
- 24 new backend tests (1349 → 1368); 0 new frontend tests (this phase
  touched no frontend code). No reduction in existing coverage -- the full
  suite, `ruff`, `lint-imports`, and the frontend's
  type-check/lint/test/build all still pass.

## Deferred, not silently skipped

- **Rate limiting beyond `auth` routes**: still process-local and
  auth-only, as ADR-0074 already decided. Broadening it (e.g. to
  `team`/`invite` routes, which are also enumeration-sensitive) is a real,
  separate scoping decision -- not bundled into this hardening pass.
- **`style-src 'unsafe-inline'`**: a nonce- or hash-based CSP for React's/
  Recharts' inline styles would remove this loosening but requires a
  build-time nonce-injection mechanism this project doesn't have yet.
- **The 20 `browser-use`-pinned CVEs**: tracked via the named
  `--ignore-vuln` list in `ci.yml` itself, not a separate tracking
  document that can drift out of sync. Revisit when `browser-use` bumps
  its own `aiohttp`/`pypdf` pins.
- **A full router-by-router business-logic-duplication audit**: only a
  spot check was done this phase; a systematic pass across every CLI
  command / API router / scheduler job pair is future work if a real
  duplication is ever found, not preemptive refactoring here.
- **Metrics/tracing beyond what ADR-0076 already added** (`/metrics`'s
  uptime/request counters): out of scope for this phase; a real
  OpenTelemetry or Prometheus-client integration is a larger, separate
  decision.
