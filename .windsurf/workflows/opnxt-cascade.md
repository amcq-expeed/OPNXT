---
description: 
auto_execution_mode: 3
---

# opnxt enterprise cascade (self-contained)

## mission
Analyze the current repository AND the authoritative OPNXT documents (listed below). Produce an enterprise-grade update that:
1) CRUDs existing code (create / read-verify / update / delete) to match the docs.
2) Implements everything “new” from the docs that is missing in code.
3) Enhances weak areas to meet enterprise NFRs (security, reliability, performance, observability, accessibility).
4) Keeps traceability, tests, docs, and deployment artifacts in lockstep.

## authoritative-docs
Only use these files as the source of truth:
- /docs/orchestrator_charter.md
- /docs/orchestrator_brd.md
- /docs/orchestrator_srs.md
- /docs/orchestrator_backlog.md
- /docs/orchestrator_tdd.md
- /docs/ai_sdlc_platform_architecture.md

If a required file is missing from /docs/, search the repo root for the same filename; otherwise mark as “missing” in outputs.

## embedded-expert-roster
Use these roles internally (no memory dependency). The “core supervisor” may call any agent rule by name.

- supervisor/enterprise-architect — state machine, phase gates, transitions
- ai-product-manager — scope, KPIs, success metrics
- business-analyst — charter/BRD interviews, acceptance criteria
- llm-engineer — provider routing, prompt safety, caching, rate limits
- backend-lead (fastapi) — orchestrator services, events, APIs
- frontend-lead (nextjs) — dashboard, chat, doc viewer, a11y
- ui-ux-designer — flows, WCAG 2.1 AA, heuristics
- data-architect — mongo/redis/gridfs/indexing, retention
- api-architect — JWT, RBAC, OpenAPI, webhooks, rate limits
- qa-lead — Gherkin, coverage≥80%, perf tests, LLM mocks
- devops — docker/compose, env parity, rollouts, secrets
- sre — health, metrics, logs, SLI/SLO, alerts
- security-lead — dep scans, key rotation, audit trails
- data-governance — traceability, impact analysis, retention
- documentation-engineer — versioning, diffs, PDF/MD export
- release-manager — stage gates, changelogs, approvals

## routing-hints
When the topic matches, call the rule(s):
- ui, wireframe, accessibility → ui-ux-agent, frontend-lead
- jwt, rbac, webhook, ratelimit → api-design-agent, security-gate
- schema, index, gridfs, retention → data-design-agent
- requirements, fr, nfr, openapi → srs-agent, api-design-agent
- stories, epics, gherkin → backlog-agent, test-planning-agent
- deploy, compose, rollout → deployment-agent, sre
- metrics, logs, alerts, slo → observability-agent
- docs, versioning, pdf → docs-agent
Always honor: enterprise-guardrails, quality-gate, security-gate.

## phase-gates
Advance only when prerequisites hold:
- charter → requirements: charter approved
- requirements → specifications: BRD complete
- specifications → design: SRS approved
- design → implementation: API/Data/UI specs ready
- implementation → testing: coverage≥0.80, integration passing
- testing → deployment: perf SLA met, security scans pass, approver signoff

## approach

### 1) repo & doc alignment
- Build a **Traceability Map**: BR→FR/NFR→Design→Code→Tests→Docs.
- Find **drift**: code not in docs (delete/deprecate candidates), docs not in code (create candidates), mismatches (update/refactor).
- Outputs:
  - `reports/traceability-map.json`
  - `reports/drift-report.md` (tables + links)

### 2) crud plan (docs are authoritative)
- **Create**: artifacts present in docs, absent in code.
- **Read/Verify**: confirm artifacts conform to contracts and NFRs.
- **Update**: refactor to match OpenAPI/DB contracts, acceptance, perf/a11y/security.
- **Delete/Deprecate**: remove obsolete endpoints/modules; add migration notes.
- Output: `plans/crud-plan.md` using this table:

| artifact | action (C/R/U/D) | spec/ref (doc+section) | owner/role | risk | tests impacted | notes |
|---|---|---|---|---|---|---|

### 3) implementation loop
For each `crud-plan` row:
- If UI/UX → `ui-ux-agent`
- If API/auth/webhooks/rate limits → `api-design-agent` + `security-gate`
- If data/schemas/retention/indexes → `data-design-agent`
- If architecture/contracts → `system-design-agent`
- If story/acceptance impacts → `backlog-agent` (+ update Gherkin)
- Enforce standards via `code-standards-agent`.
- Use atomic commits with messages referencing FR/BR IDs.

### 4) testing (shift left)
- Generate/update tests from requirements (Gherkin → unit/integration/perf).
- Mock LLM/external services where needed.
- Targets: coverage≥80%, build success≥95%, p95 latency within budget per endpoint.
- Outputs: test files + `reports/coverage.html` + `reports/perf-results.md`.
- Gate: `quality-gate`.

### 5) security & compliance
- JWT, RBAC, TLS1.3; dependency scan; no secrets in repo; encryption-at-rest where applicable; rate limits; audit trails.
- Outputs: `security/dependency-scan.json`, `security/findings.md`, `SECURITY.md`.
- Gate: `security-gate`.

### 6) observability & operations
- Health endpoints, metrics, structured logs, tracing, alerts, SLO dashboards.
- Outputs: `ops/prometheus/`, `ops/grafana/`, `ops/logging/`, `ops/runbooks/`.
- Call: `observability-agent`, `deployment-agent`.

### 7) documentation & versioning
- Update `README.md`, `CHANGELOG.md`; generate PDFs/MD; produce diffs for any modified doc.
- Call: `docs-agent`.

### 8) traceability & impact
- Regenerate matrix; include impact of every change.
- Outputs: updated `reports/traceability-map.json`, `reports/impact-analysis.md`.
- Call: `traceability-agent`.

### 9) deliverables (bundle)
- `plans/crud-plan.md`
- `reports/drift-report.md`
- `reports/impact-analysis.md`
- `reports/coverage.html`
- `reports/perf-results.md`
- `security/findings.md`
- `ops/*` (monitoring + runbooks)
- Updated code/tests/docs/docker/openapi etc.

## quality-bars (hard gates)
- unit coverage ≥ 80%
- build success rate ≥ 95%
- p95 latency meets target for each endpoint (define & measure)
- security scans pass; no secrets present
- docs updated; traceability complete
- all gates green: enterprise-guardrails + quality-gate + security-gate

## enhancement-heuristics
When specs are thin or weak:
- propose & implement low-risk improvements that reduce latency/cost, improve a11y/UX clarity, harden RBAC, or increase observability.
- never break published contracts; guard risky changes behind feature flags.

## output format
1) Post a concise summary of repo vs. docs drift and the CRUD plan.
2) Implement in small PRs; after each PR, run checks and post status.
3) Conclude with a Release Candidate tag proposal and deployment checklist.

## permissions
- The core supervisor may call any rule and chain calls.
- Prefer “Model Decision” for agent rules; “Always On” for core/guards.
- Always enforce enterprise-guardrails, quality-gate, and security-gate.
