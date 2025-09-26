---
title: OPNXT Branching Strategy
author: Cascade
last_updated: 2025-09-26
---

# Purpose

This guide documents the branching and pull-request workflow required to align OPNXT delivery with the enterprise SDLC guardrails (`core-supervisor`, `quality-gate`, `security-gate`). All contributors must follow this process for every change.

# Roles

- **Feature Authors**: create feature branches, implement changes, and submit pull requests (PRs).
- **Reviewers**: confirm code quality, coverage, security, and documentation updates before approval.
- **Maintainers**: enforce branch protection rules, merge approved PRs, and monitor CI health.

# Flow Overview

1. Sync local `main` (or the current release branch) with origin.
2. Create a short-lived branch for the task using the naming convention below.
3. Commit scoped changes with descriptive messages referencing tickets or requirements IDs.
4. Push the branch and open a PR against the protected target branch.
5. Ensure all CI checks (tests, coverage, security scan, lint) succeed and documentation is updated.
6. Request review. At least one maintainer must approve before merge.
7. After merge, delete the feature branch to keep the repository tidy.

# Branch Naming

- **Features**: `feature/<short-context>-<ticket>` (e.g., `feature/mvp-chat-layout-123`).
- **Bug fixes**: `bugfix/<component>-<issue>` (e.g., `bugfix/deploy-script-python-path`).
- **Hotfixes** (production defects): `hotfix/<issue-id>` and require maintainer approval plus post-merge retro.

# Pull Request Expectations

- Provide a summary, linked work items, testing evidence, and risk/rollback notes.
- Reference updated artifacts (e.g., SRS, docs) and traceability updates when relevant.
- Confirm the following checkboxes before requesting review:
  - Unit/integration tests passing.
  - Coverage ≥ 80% maintained per `quality-gate`.
  - `security-gate` scans clean (dependency, secret detection).
  - Documentation and CHANGELOG (if applicable) updated.
  - Impact analysis and next actions documented.

# Branch Protection Settings (Recommended)

Configure GitHub branch protections for `main` (and release branches):

- Require PR reviews (≥1 maintainer) before merge.
- Block direct pushes.
- Require status checks to pass before merging: CI workflow, security scan, lint, coverage report.
- Require conversations to be resolved and signed commits if organizational policy mandates it.
- Enable branch deletion on merge to reduce clutter.

# Handling Releases

- Cut release branches `release/<version>` once feature scope is frozen.
- Only backport critical fixes to release branches via PRs.
- Tag releases with semantic version tags (e.g., `v1.2.0`) after validation.

# Emergency Procedure

If a critical fix must bypass normal flow, coordinate with maintainers to:

1. Create a `hotfix/` branch.
2. Run targeted CI (tests, security snippet) locally if pipeline is too slow.
3. Open a PR labeled `hotfix` and secure expedited reviews.
4. Merge only after explicit approval from `quality-gate` and `security-gate` owners.
5. Retroactively update documentation and traceability.

# Tooling Tips

- Use `git switch -c feature/...` to create branches.
- Configure local hooks (pre-commit, lint) to catch issues early.
- Keep branches under ~200 LOC changes when possible for review efficiency.

# Compliance Reminder

Following this branching strategy is mandatory to pass enterprise audits and maintain traceability across requirements, code, and tests. Deviations must be documented and approved by project leadership.
