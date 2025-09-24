# Drift Report (Repo vs. Authoritative Docs)

- Scope: docs under `docs/Claude/` are the source of truth (Charter/BRD/SRS/TDD/Backlog/Architecture).
- Current app includes Streamlit UI (`main.py`) and a new FastAPI backend (`src/orchestrator/api/main.py`) with `/health`, `/metrics`, and `/projects` CRUD + phase advance. JWT/RBAC not yet implemented; no DB/Redis; no WebSocket; observability is partial via Prometheus metrics endpoint.

## Highlights
- Present: `src/sdlc_generator.py`, `src/validate_docs.py`, `src/phase_guides.py`, `src/backlog.py`, `src/discovery_agent.py`, `main.py`, CI workflow.
- New: FastAPI backend with routers (`src/orchestrator/api/routers/projects.py`), in-memory repository (`src/orchestrator/infrastructure/repository.py`), state machine (`src/orchestrator/core/state_machine.py`), Prometheus metrics at `/metrics`, health at `/health`.
- Missing (per SRS/TDD): Auth (JWT), RBAC, Agent registry/core, MongoDB/GridFS, Redis cache, Webhooks, Versioning, Traceability matrix, Perf tests.
- Docs location drift: expected `/docs/*` but authoritative are in `docs/Claude/*` → treat as canonical.
- Tests: API smoke tests added (`tests/test_api.py`), overall coverage still << 80% (quality-gate red).
- Security: no secrets committed (good), but JWT/RBAC/TLS not implemented (security-gate red).

## Counts
- FR present: 5 (FR-003, FR-008, FR-013, FR-014, FR-016)
- FR partial: 2 (FR-004, FR-005)
- FR missing: 10 (see traceability-map.json)
- NFR gaps: authn/z, tls, perf SLOs, reliability; observability partial via metrics endpoint.

## Recommendations (next PRs)
- Add FastAPI backend skeleton + health/metrics + minimal `/projects` in-memory.
- Add JWT auth stubs + RBAC decorator; wire to endpoints.
- Add traceability CLI + reports generation.
- Add unit tests + coverage gate; perf smoke timings for p95 targets.
