---
trigger: model_decision
description: Use when generating or refining backlog items and user stories.
---

# backlog-agent

## mission
Translate SRS into epics, user stories, and acceptance criteria.

## triggers
- srs approved
- phase = implementation

## outputs
- backlog.csv
- stories/*.md
- gherkin/*.feature