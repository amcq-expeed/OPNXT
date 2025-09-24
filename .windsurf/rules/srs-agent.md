---
trigger: model_decision
description: Generate or refine the Software Requirements Specification.
---

# srs-agent

## mission
Produce Software Requirements Specification (SRS) with FRs and NFRs.

## triggers
- phase = specifications
- brd completed

## outputs
- srs.md
- srs.pdf
- fr_list (FR-*)
- nfr_list (NFR-*)