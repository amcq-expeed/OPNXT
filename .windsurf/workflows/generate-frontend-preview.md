---
description: request ready-to-run frontend bundle with live mock preview via Design & Build Guidance accelerator
---

1. Open Design & Build Guidance accelerator in Chrome MCP.
2. Submit feature prompt describing backend, frontend, and preview requirements. Include explicit instruction: “Please package the frontend into a ready-to-run bundle and include the live HTML preview so stakeholders can interact with the mock UI.”
3. When the assistant requests specifics, provide concrete metric/data values and restate the bundle + preview requirement.
4. Wait for artifacts to stream. Verify artifacts list now includes:
   - `*-bundle.zip` (bundle type)
   - `*-preview.html` (preview type)
5. Select the HTML preview artifact to confirm the live mock renders inside the drawer iframe.
6. Download ZIP bundle if needed for local run.
