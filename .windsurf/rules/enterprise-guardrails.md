---
trigger: always_on
---

# enterprise-guardrails

## activation
always-on

## mission
Enforce enterprise-wide non-functional requirements (NFRs).

## checks
- performance: chat <=3s, doc-gen <=10s, dashboard <=2s
- security: jwt, rbac, tls1.3, encryption-at-rest, no secrets in repo, dependencies scanned
- reliability: uptime >=99.5%, rto <=60m, rpo <=15m

## actions
If any check fails:
- call quality-gate and security-gate
- block merge or deploy until resolved
