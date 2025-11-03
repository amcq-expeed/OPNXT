# Operations Runbooks

- API Health Check: Call `GET /health` and verify `status: ok`.
- Metrics: Scrape `GET /metrics` with Prometheus.
- Incident: On API failure, collect logs, endpoints status, and recent changes.
- Rollback: Revert to previous image/artifacts, verify `health` endpoint, and monitor.
- Backend Service: Ensure Windows service `opnxt-backend` is running (created by `scripts/deploy-uat.ps1` via NSSM). Restart with `Start-Service opnxt-backend` or `Restart-Service opnxt-backend`.
- Backend Environment: Confirm `OPNXT_ENV_FILE` in service configuration points to `C:\opnxt\.env` after deployment.
- Frontend Static Assets: IIS site `opnxt` should point to `C:\opnxt\frontend\wwwroot`; rerun deployment script to refresh assets.
