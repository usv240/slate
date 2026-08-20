# Deployment

SLATE uses two independently recoverable tiers in GCP `us-central1`.

1. Cloud Run hosts FastAPI, FFmpeg, Google ADK, Gemini on Vertex AI, Firestore
   state, and the pinned official Grafana MCP binary.
2. A dedicated Compute Engine VM runs the tracked `observability/` Compose stack:
   Caddy, Grafana, Prometheus, Loki, Tempo, and Alloy.

Cloud Run's service account requires `roles/aiplatform.user`,
`roles/datastore.user`, and accessor permission on only
`slate-grafana-service-account-token`. The observability VM service account has
no project roles. Firewall ingress exposes only TCP 80/443; no Grafana backend or
telemetry port is public.

The VM can be rebuilt by copying `observability/`, creating an untracked `.env`
with `SLATE_DOMAIN`, `SLATE_OTLP_PATH`, and `GRAFANA_ADMIN_PASSWORD`, then running
`bootstrap.sh`. Rotate the Grafana service-account token in Grafana and Secret
Manager after rebuilding.

Acceptance checks:

```text
GET /health
GET /v1/integrations/grafana/evidence
GET /metrics
```

`/health` is passing only after a real Vertex generation and official MCP PromQL
round-trip. `docs/LIVE-ACCEPTANCE.json` is a redacted record of the last complete
judge-path verification.
