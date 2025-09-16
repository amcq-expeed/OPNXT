# Change Tracker

Track decisions, revisions, and their impact across artifacts. Use this to keep alignment during iterative work.

## Purpose
- Maintain a single source of truth for changes and rationale.
- Link changes to artifacts (SRS, SDD, Test Plan, Code) and owners.

## Change Log Template
| Date | Area | Description of Change | Reason / Context | Impacted Artifacts | Owner |
|------|------|-----------------------|------------------|--------------------|-------|
| 2025-09-16 | Requirements | Updated Feature A scope | User feedback reduced scope | SRS.md, TestPlan.md | PM |

## Workflow
1. Propose change in chat or PR description.
2. Log change in the table above.
3. Update impacted artifacts.
4. Run validation checklist again.
5. Confirm downstream updates (tests, CI, docs).

## Prompts (Use These in Chat)
- "Log a change: <short description>. What artifacts are impacted?"
- "Summarize all changes since last commit and list impacted areas."
- "Create follow-up tasks for each impacted artifact."

## Definition of Done
- Change is logged with rationale and owner.
- Impacted artifacts updated or tasks created.
- Validation re-run if applicable.
