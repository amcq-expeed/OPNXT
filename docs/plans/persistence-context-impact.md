# Plan: Persistence and Context/Impact Features

Date: 2025-09-19
Owner: Orchestrator Team
Status: Prioritized / Ready for implementation

## Goals
- Add durable persistence for projects and documents with versioning.
- Implement context management (FR-006) and change impact analysis (FR-012).
- Keep the in-memory implementation as a default; switchable via `OPNXT_REPO_IMPL`.

## Scope
1) Persistence Layer
- Implement `MongoProjectRepository` using `pymongo` (or `motor` if async later), enabled with `OPNXT_REPO_IMPL=mongo`.
- Collections:
  - `projects` (project metadata and current phase)
  - `documents` (per-project artifact metadata + versioning)
  - `blobs` via GridFS for artifact content (markdown and optional PDFs)
- Add repository methods:
  - `save_document(project_id, filename, content, meta)` → returns version id
  - `list_documents(project_id)` → versions and meta
  - `get_document(project_id, filename, version=None)` → return content + meta

2) Context Management (FR-006)
- Add `ContextStore` abstraction with repository-backed persistence:
  - `get_context(project_id)`
  - `put_context(project_id, context_dict)`
- Surface routes:
  - `GET /projects/{id}/context` → returns context pack (answers, summaries, overlays)
  - `PUT /projects/{id}/context` → upsert context pack
- Integrate with doc generation to pull the latest context when generating artifacts.

3) Change Impact Analysis (FR-012)
- Minimal viable approach:
  - Parse the `reports/traceability-map.json` (FR IDs → artifacts, code). 
  - Given a set of changed FRs or document sections, compute affected artifacts (SRS, SDD, TestPlan) and code areas.
- Add `POST /projects/{id}/impacts` with payload:
  ```json
  { "changed": ["FR-003", "FR-011"], "strategy": "heuristic" }
  ```
  - Response lists impacted docs and modules with a confidence score.

## Data Model (initial)
- projects:
  - `_id`, `project_id`, `name`, `description`, `status`, `current_phase`, `created_at`, `updated_at`, `metadata`
- documents:
  - `_id`, `project_id`, `filename`, `version`, `created_at`, `meta` (hash, size, contentType), optional references
- blobs: GridFS keyed by document `_id` + `version`
- contexts:
  - `_id`, `project_id`, `data` (free-form JSON), `updated_at`

## Acceptance Criteria
- Switching `OPNXT_REPO_IMPL=mongo` persists projects; CRUD + phase advance backed by Mongo.
- Generating documents writes artifacts and versions in Mongo/GridFS; `GET /projects/{id}/documents` lists current versions.
- `GET/PUT /projects/{id}/context` roundtrips a context JSON payload; `POST /projects/{id}/documents` uses stored context.
- `POST /projects/{id}/impacts` returns impacted docs/modules for a provided FR list.
- Tests: repository unit tests (memory + mongo), API tests for context and impacts, and integration tests for doc versioning. Coverage remains ≥ 80%.

## Risks / Mitigations
- Mongo availability in CI: Use ephemeral MongoDB (e.g., GitHub Actions service) and fallback skip if unavailable; keep memory default.
- Versioning growth: Retention policy simple cap per artifact (e.g., last N versions) configurable via env.
- Security: Ensure no secrets checked in; use RBAC on new routes (context read/write, impact compute requires project:read).

## Phasing
- Phase A (1-2 days): ContextStore + routes, wire into doc generation; tests.
- Phase B (2-3 days): Change impact service + route; tests; traceability update to mark FR-006/FR-012 partial/present.
- Phase C (3-5 days): Mongo repository for projects + documents + GridFS; env toggle; tests.

## Follow-ups
- Export OpenAPI with the new routes.
- UI updates in Next.js to edit/view context and show impact analysis results.
