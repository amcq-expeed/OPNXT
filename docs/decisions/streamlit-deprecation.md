# Decision: Deprecate Streamlit UI and Consolidate on Next.js

Date: 2025-09-19
Status: Approved / In progress

## Context
The target architecture specifies a React/Next.js frontend. A parallel Streamlit app (`main.py`) has served as a demo surface but now creates duplication, divergent UX, and maintenance drag. The Next.js UI already implements the required flows: authentication, project CRUD, document generation, artifact download, and agent registry.

## Decision
- Streamlit UI is deprecated effective immediately.
- Remove Streamlit from default `requirements.txt` to prevent accidental use and heavy native dep installs.
- Keep `main.py` in-repo for reference during a short transition period. No CI or traceability credit relies on it anymore.
- All new UI work happens in `frontend/` (Next.js). A future cleanup task will remove Streamlit code entirely once parity is reached.

## Rationale
- Aligns with the architecture doc and enterprise UX standards.
- Reduces dependency weight and build issues (WeasyPrint, Streamlit system deps).
- Focuses engineering effort on a single, modern frontend stack.

## Consequences
- Local dev must use the Next.js client: `cd frontend && npm run dev` (or via existing scripts).
- Any Streamlit-specific paths in docs should be updated; samples and screenshots will reference the Next.js UI.

## Migration Plan
- Short term: Show deprecation notice in documentation. (This doc.)
- Update traceability to map UI/Chat/Viewer to Next.js pages. (Done)
- Remove `streamlit` from `requirements.txt`. (Done)
- Remove WeasyPrint from defaults; keep optional PDF path. (Done)
- Follow-up: optionally gate `main.py` execution behind an env flag, then remove after one milestone.

## Rollback Plan
- Re-add Streamlit and WeasyPrint deps if a blocking regression is found in the Next.js UI. Not expected.
