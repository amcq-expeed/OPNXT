# CRUD Plan (Authoritative Docs → Code)

| artifact (path or name) | action (C/R/U/D) | spec/ref (doc §) | owner/role | risk (L/M/H) | tests impacted | notes |
|---|---|---|---|---|---|---|
| `src/orchestrator/api/main.py` (FastAPI app) | C | SRS §5 API-001; TDD §5 | api-design-agent | M | integration: auth, projects | Bootstrap REST API + `/health`, `/metrics` |
| `src/security/auth.py` (JWT) | C | SRS NFR-003 | security-gate | H | unit: token, middleware | Use `python-jose` or `pyjwt` + `passlib[bcrypt]` |
| `src/security/rbac.py` | C | SRS NFR-004 | security-gate | M | unit: RBAC checks | Role -> permission map + decorator |
| `src/orchestrator/state_machine.py` | C | SRS Appx B | system-design-agent | M | unit: transitions | Enforce phase gates |
| `src/agents/{base,charter}.py` + `src/agents/registry.py` | C | SRS §3.3 FR-005 | system-design-agent | M | unit: agent select | Wrap existing `discovery_agent` where possible |
| `src/storage/repository.py` (Mongo stub) | C | SRS FR-010 | data-design-agent | M | integration: repo | Start in-memory; feature flag Mongo |
| `src/cache/redis_client.py` | C | SRS §2.1 | data-design-agent | L | unit: cache | Optional for MVP |
| `.github/workflows/ci.yml` (coverage gate) | U | quality-gate | code-standards-agent | L | ci | Enforce ≥75% coverage threshold |
| `requirements.txt` (FastAPI, auth, db, obs) | U | TDD §8 | deployment-agent | M | ci | Add fastapi, uvicorn, pydantic, pyjwt, passlib[bcrypt], prometheus_client |
| `Dockerfile` + `docker-compose.yml` | U/C | TDD §8.2 | deployment-agent | M | e2e | Add backend service, healthcheck |
| `tests/` (unit/integration/perf) | C | Backlog Epic 5 | test-planning-agent | M | all | Mock LLM, stub DB/Redis |
| `ops/prometheus/` + `ops/runbooks/` | C | TDD §10 | observability-agent | L | n/a | Metrics, alerts, runbooks |
