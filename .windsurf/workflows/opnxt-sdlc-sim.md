---
description: Run the OPNXT headless SDLC simulation and produce docs, code, tests, and CI
---
# OPNXT SDLC Simulation (Headless)

This workflow runs the full OPNXT pipeline without the Streamlit UI.
It will generate SDLC documents, validate them, produce code scaffolds, generate pytest tests, and scaffold a GitHub Actions CI workflow.

## Prerequisites
- Python 3.11+
- Install dependencies in the repository root:
  - Windows PowerShell: `pip install -r requirements.txt`

## Steps
1. Run the SDLC simulation script
   Command (from repository root):
   - Windows PowerShell:
     ```powershell
     python scripts/simulate_sdlc.py
     ```

2. Review generated outputs
   - SDLC docs in `docs/` (e.g., `ProjectCharter.md`, `SRS.md`, `SDD.md`, `TestPlan.md`)
   - Validation report: `docs/validation_report.json`
   - JSON bundle: `docs/sdlc_bundle.json`
   - Generated code in `generated_code/` (includes a runnable Streamlit app)
   - Tests in `tests/generated_tests/`
   - CI workflow: `.github/workflows/ci.yml`

3. Run the generated app locally
   - Windows PowerShell:
     ```powershell
     streamlit run generated_code/webapp/streamlit_app.py
     ```

4. Run tests locally
   - Windows PowerShell:
     ```powershell
     pytest -q
     ```

5. Optional: Commit and push to trigger CI
   - Ensure you have a GitHub repo configured.
   - Commit the generated artifacts and push to `main` to run CI.
