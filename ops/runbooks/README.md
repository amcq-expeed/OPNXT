# Operations Runbooks

- API Health Check: Call `GET /health` and verify `status: ok`.
- Metrics: Scrape `GET /metrics` with Prometheus.
- Incident: On API failure, collect logs, endpoints status, and recent changes.
- Rollback: Revert to previous image/artifacts, verify `health` endpoint, and monitor.
