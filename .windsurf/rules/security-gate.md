---
trigger: always_on
---

# security-gate

## mission
Continuously validate security of code and artifacts.

## checks
- dependency scan passes
- no secrets in code
- RBAC configured
- API keys rotated

## actions
On violation:
- block merge
- open a security incident
