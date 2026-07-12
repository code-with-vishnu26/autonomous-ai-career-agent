# Production Deployment (Phase 59, ADR-0076)

## Overview

```
Browser -> Nginx (edge, TLS-ready) -> React (static, nginx) / FastAPI (gunicorn + uvicorn workers) -> SQLite -> Browser Automation
```

Single-host Docker Compose deployment. There is no orchestration
(Kubernetes/Nomad) layer in this project -- that is out of scope for this
phase and not implied by anything here.

## 1. Prepare your environment file

```bash
cp production.env.example production.env
```

Fill in, at minimum:

- `JWT_SECRET_KEY` -- generate with
  `python -c "import secrets; print(secrets.token_urlsafe(32))"`. The API
  refuses to sign/verify sessions without it (fails closed, both at
  startup validation and per-request).
- `GROQ_API_KEY` or `ANTHROPIC_API_KEY` -- required for tailoring, the
  truthfulness gate, and the Career Coach's AI-backed features.
- `CLI_LOCAL_USER_EMAIL` -- the CLI's fixed auto-provisioned account
  email (only matters if you also run `career-agent prepare`/`review`/
  `submit` against this same database).

**Never commit `production.env`** -- it's gitignored
(`!production.env.example` is the only tracked variant).

## 2. HTTPS

This repository ships no certificate. To terminate TLS at the edge:

1. Obtain a real certificate (Let's Encrypt/certbot, or your own CA).
2. Mount it into the `nginx` container:
   ```yaml
   # docker-compose.prod.yml already has this commented; uncomment it:
   nginx:
     ports:
       - "443:443"
     volumes:
       - ./certs:/etc/nginx/certs:ro
   ```
3. Replace `deploy/nginx/edge.conf` with `deploy/nginx/edge-tls.conf.example`
   (copy it over, updating `server_name` for your domain).
4. Set `JWT_COOKIE_SECURE=true` in `production.env` -- the refresh-token
   cookie is only sent over HTTPS once this is on (browsers refuse to
   send a `Secure` cookie over plain HTTP either way, so this must match
   reality).
5. Rebuild the `nginx` service:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml build nginx
   ```

Generating a self-signed certificate automatically was deliberately not
done -- that would present as "secured" without actually being trusted by
any real browser, a false signal this project's own discipline refuses to
ship.

## 3. Database: SQLite (default) or PostgreSQL (not yet consumed)

**SQLite is the only backend the storage layer actually reads from or
writes to today.** `DATABASE_URL` is accepted in configuration and
validated (a startup warning fires if you set it), but nothing in
`storage/sqlite.py` consumes it -- see ADR-0076 for why (the storage
layer is ~15 store classes built directly on the stdlib `sqlite3` module,
with no database-abstraction layer to swap a driver underneath; real
PostgreSQL support would mean duplicating every store or rewriting the
whole storage layer, both explicitly out of scope for an infrastructure
phase).

The `postgres` Compose service exists and is startable
(`docker compose --profile postgres up`) so the infrastructure shape is
present, but it is not wired to the application. If you enable it today,
your data still lives in the SQLite volume, not Postgres.

Persist SQLite reliably in production the same way the base compose file
already does: the named `career_agent_data` volume, not a bind mount to
somewhere that might get wiped.

## 4. Start the stack

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  --env-file production.env up -d --build
```

`docker-compose.prod.yml` sets `ENVIRONMENT=production`,
`JSON_LOGS=true`, `JWT_COOKIE_SECURE=true`, `restart: always` on every
service, and CPU/memory limits.

## 5. Verify

```bash
curl -f http://your-host/health
curl -f http://your-host/ready
docker compose ps   # every service should show (healthy)
```

## 6. Backups

The SQLite database is a single file inside the `career_agent_data`
volume. Back it up with any standard volume-backup approach, e.g.:

```bash
docker run --rm -v career_agent_data:/data -v "$PWD":/backup alpine \
  tar czf /backup/career_agent-backup-$(date +%F).tar.gz -C /data .
```

Stop the `backend` container first (or accept an eventually-consistent
snapshot) -- SQLite doesn't guarantee a consistent file-level copy of a
database being actively written to.

## 7. Updating

```bash
git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  --env-file production.env up -d --build
```

Rolling/zero-downtime deploys are out of scope (single-host Compose, not
an orchestrator) -- there will be a brief window where `backend` restarts.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `backend` container unhealthy | Missing/invalid `JWT_SECRET_KEY`, or the database volume isn't writable | `docker compose logs backend`; check `startup validation` warnings/errors in the first log lines |
| `401` on every dashboard request | `JWT_SECRET_KEY` differs between restarts (regenerated) | Set it once in `production.env`, don't regenerate on every deploy |
| Refresh cookie never persists | `JWT_COOKIE_SECURE=true` but you're not actually on HTTPS | Either terminate TLS (section 2) or set it back to `false` for plain-HTTP testing |
| Tailoring/Coach AI features report unavailable | No `GROQ_API_KEY`/`ANTHROPIC_API_KEY` set | Set one; deterministic Coach features (Resume Analysis, Job Match, Skill Gap) work without either |
| `nginx` 502 on `/api/*` | `backend` isn't healthy yet, or crashed | `docker compose logs backend`; `nginx`'s `depends_on: service_healthy` should already prevent routing to a not-yet-ready backend, but a crash after startup isn't caught by that |
| Postgres/Redis containers running but nothing changes | Expected -- neither is consumed yet (see section 3) | Not a bug; see ADR-0076 |
