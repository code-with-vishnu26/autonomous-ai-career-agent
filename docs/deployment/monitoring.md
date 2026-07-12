# Monitoring (Phase 59, ADR-0076)

## Health endpoints

| Path | Purpose | Checks | Backing |
|---|---|---|---|
| `GET /health` | Container liveness probe | Process is up. Nothing else | `api/routers/health.py::liveness` |
| `GET /api/health` | Unchanged from Phase 54 | Same as `/health` | `api/routers/health.py::health` -- the frontend already calls this; kept for backward compatibility |
| `GET /ready` | Container readiness probe | Opens the SQLite database at `DATABASE_PATH` (creates if absent, same connection every real store makes) | `api/routers/health.py::readiness` -- returns `503` (not a falsely-green `200`) the instant that fails |
| `GET /metrics` | Prometheus scrape target | Process uptime, request counts by status class | `api/routers/health.py::metrics` |

`Dockerfile.backend`'s own `HEALTHCHECK` uses `/health` (liveness only);
`docker-compose.yml` overrides it with `/ready` for the `backend` service
specifically, so `frontend`'s `depends_on: condition: service_healthy`
waits for "can actually serve," not just "process is up."

## Structured logging

`core/logging_config.py::configure_logging` sets up the root logger once,
at process start (`api/app.py`'s `_lifespan` startup hook, and
`career-agent serve`'s own entrypoint). JSON by default in
`ENVIRONMENT=production` (or with `JSON_LOGS=true` regardless of
environment); one JSON object per line, matching what every container log
collector (Docker, Kubernetes, CloudWatch) already expects -- no new
dependency (`structlog`/`python-json-logger`), a small stdlib
`logging.Formatter` subclass instead.

Example JSON log line:

```json
{"timestamp": "2026-07-13T10:00:00+00:00", "level": "INFO", "logger": "career_agent.api.requests", "message": "GET /coach/resume-analysis -> 200", "method": "GET", "path": "/coach/resume-analysis", "status_code": 200, "duration_ms": 42.31}
```

### Request logging

`api/middleware.py::log_requests` logs one line per request: method,
path, status code, duration in ms. **Never logs headers or the request/
response body** -- those can carry an access token, a refresh cookie, a
password, or an LLM API key.

### Startup logging

Every finding from `core/startup_validation.py::validate_startup` is
logged (warning or error level) at process start -- see
`environment.md`'s "Missing-variable warnings" section for the full list.

### Error logging

Unhandled exceptions in a route surface through FastAPI's own default
exception handling (a `500` response) and through gunicorn's
`--error-logfile -` (stdout, wired in `Dockerfile.backend`'s `CMD`) for
anything at the process/worker level.

## Prometheus metrics

`GET /metrics` returns the standard Prometheus text-exposition format:

```
# HELP career_agent_uptime_seconds Process uptime in seconds.
# TYPE career_agent_uptime_seconds gauge
career_agent_uptime_seconds 1234.56
# HELP career_agent_requests_total Requests observed, by status class.
# TYPE career_agent_requests_total counter
career_agent_requests_total{status="2xx"} 42
career_agent_requests_total{status="4xx"} 3
```

Deliberately minimal -- no `prometheus_client` dependency, no
histograms/labels beyond status class. This is process-local, in-memory,
and reset on restart: with gunicorn's 4 worker processes, `/metrics`
reports whichever worker answered that particular request's counters, not
an aggregate across all four. That's an honest limitation of a
zero-dependency counter, not a bug -- a real multi-instance/multi-worker
deployment that wants accurate aggregate metrics should adopt
`prometheus_client`'s multiprocess mode outright rather than growing this
hand-rolled counter to fake what that library already does correctly.
Named here as a real, deferred follow-up, not built speculatively.

### Wiring an actual Prometheus scrape (optional)

Nothing in this repository runs a Prometheus server -- this endpoint only
exposes the metrics format. To actually scrape it, point your own
Prometheus instance at `http://<your-host>/metrics` (through the edge
nginx, which proxies it to the backend, `deploy/nginx/edge.conf`), e.g.:

```yaml
scrape_configs:
  - job_name: career-agent
    static_configs:
      - targets: ["your-host:80"]
    metrics_path: /metrics
```

## Container-level health

Every image in this stack declares a `HEALTHCHECK` (`Dockerfile.backend`,
`Dockerfile.frontend`, `deploy/nginx/Dockerfile`) so `docker compose ps`
and `docker inspect --format='{{json .State.Health}}' <container>` report
real status, and `depends_on: condition: service_healthy` (used by
`frontend`'s dependency on `backend` in `docker-compose.yml`) actually
waits on it.
