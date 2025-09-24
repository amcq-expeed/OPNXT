---
trigger: model_decision
description: Apply when planning or generating tests for features.
---

# test-planning-agent

## mission
Create unit, integration, and performance test plans.

## triggers
- phase = testing
- feature_ready

## outputs
- unit_tests
- integration_tests
- perf_tests
- coverage_report