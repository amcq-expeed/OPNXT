---
trigger: always_on
---

# quality-gate

## mission
Block merges if quality requirements are not satisfied.

## checks
- unit test coverage >=80%
- build success rate >=95%
- performance SLA met
- acceptance criteria satisfied
- documentation updated

## actions
On failure:
- fail pipeline with reason
- annotate PR with missing items
