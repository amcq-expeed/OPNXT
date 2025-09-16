# Deployment Guide

This project includes a generated Streamlit app scaffold and CI. Below are deployment options.

## Local Development

1. Install dependencies:
   - Windows PowerShell:
     ```powershell
     pip install -r requirements.txt
     ```
2. Run the generated app:
   ```powershell
   streamlit run generated_code/webapp/streamlit_app.py
   ```
3. Run tests locally:
   ```powershell
   pytest -q
   ```

## GitHub Actions CI

A workflow is scaffolded at `.github/workflows/ci.yml`.
- On pushes and PRs to `main`/`master`, CI installs dependencies and runs pytest.
- Extend this workflow to add linting, type checks, and deploy steps.

## Streamlit Community Cloud (Easy)

1. Push this repository to GitHub.
2. Go to https://share.streamlit.io and deploy a new app.
3. App path: `generated_code/webapp/streamlit_app.py`.
4. Python version: 3.11, and ensure `requirements.txt` is used.

## Docker (Containerized)

A simple `Dockerfile` is provided to run the generated app.

Build:
```powershell
docker build -t opnxt-generated-app .
```

Run:
```powershell
docker run --rm -p 8501:8501 opnxt-generated-app
```

Open http://localhost:8501 in your browser.

## Render / Fly.io / Railway

- Use the provided Dockerfile.
- Expose port 8501.
- Start command (if asked):
  ```bash
  streamlit run generated_code/webapp/streamlit_app.py --server.port 8501 --server.address 0.0.0.0
  ```

## Next Steps

- Replace the in-memory feature list with a backend (e.g., FastAPI + SQLite/Postgres).
- Add API tests and integration tests.
- Add observability (logging/metrics) and secrets management for production.
