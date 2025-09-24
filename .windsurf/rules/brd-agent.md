---
trigger: model_decision
description: Apply when expanding business requirements into a BRD.
---

# brd-agent

## mission
Generate Business Requirements Document (BRD).

## triggers
- charter approved
- phase = requirements

## outputs
- brd.md
- brd.pdf
- req_list (BR-*)

## constraints
Cannot run without approved charter.