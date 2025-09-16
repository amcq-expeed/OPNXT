# Validation Checklist

Use this checklist to review generated artifacts and feature proposals before moving forward.

## Purpose
- Provide a fast quality gate after generation or drafting.
- Catch missing sections, unclear requirements, and risky assumptions.

## General Checks
- [ ] Scope and goals are explicit and testable
- [ ] Assumptions and constraints are listed
- [ ] Stakeholders and users are identified
- [ ] Success metrics and KPIs defined
- [ ] Risks and mitigations captured
- [ ] Open questions tracked with owners

## SRS (Requirements) Checks
- [ ] Functional requirements are prioritized and unambiguous
- [ ] Non-functional requirements include performance, security, compliance
- [ ] Acceptance criteria present for key features

## SDD (Design) Checks
- [ ] Architecture overview and diagrams present
- [ ] Data model and API surface defined
- [ ] Integration points and dependencies clear
- [ ] Key trade-offs and decisions documented

## Test Plan Checks
- [ ] Unit, integration, and e2e coverage strategy
- [ ] Test data and environment requirements
- [ ] Entry/exit criteria defined

## Deployment/Operations Checks
- [ ] Release strategy (staged/blue-green/canary)
- [ ] Monitoring/observability
- [ ] Rollback plan

## Prompts (Use These in Chat)
- "List what’s missing in the SDD under Architecture/Data/API."
- "Generate acceptance criteria for the top 3 features."
- "Summarize risks and propose mitigations."

## Definition of Done
- All critical checks are ✅ or have explicit exceptions with owner and timeline.
