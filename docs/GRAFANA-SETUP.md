# Live Grafana integration and recovery runbook

The judging stack is live at `https://35-255-68-247.sslip.io`. It runs Grafana
OSS, Prometheus, Loki, Tempo, Alloy, and Caddy on a dedicated GCP VM. The rules
explicitly permit this unattended pattern with the official open-source MCP
server and a service-account token. Never place tokens in this repository or a
command transcript.

## Pinned runtime

The Cloud Run image contains the official `grafana/mcp-grafana` binary pinned to
`1.1.0` and copied from Grafana's published container image. The application
starts it over stdio only when `GRAFANA_MCP_COMMAND` is configured.

## Required non-secret settings

```text
GRAFANA_MCP_COMMAND=/usr/local/bin/mcp-grafana -t stdio
GRAFANA_URL=https://35-255-68-247.sslip.io
GRAFANA_PROMETHEUS_UID=slate-prometheus
GRAFANA_LOKI_UID=slate-loki
GRAFANA_TEMPO_TOOL=tempo_get-trace
```

The Tempo tool is proxied and its advertised name may have a prefix. SLATE lists
the server's tools and accepts only an exact match or one unique suffix.

## Secrets

Create the Grafana service-account token in Google Secret Manager and mount it as
the `GRAFANA_SERVICE_ACCOUNT_TOKEN` environment variable on Cloud Run. Use an
Editor service account for the hackathon integration test, then reduce it to the
documented RBAC scopes after the exact tool set is stable. Do not paste the token
into chat, source, `.env`, or a deployment command.

Minimum demonstrated surface:

- `query_prometheus` for schedule budget and burn;
- `query_loki_logs` for the real FFmpeg/QC failure;
- the advertised Tempo trace lookup tool;
- `create_annotation` after explicit human approval;
- `create_incident` or `alerting_manage_rules` for a real write beyond annotation.

Grafana Incident and Sift write operations require Editor. Fine-grained access
for datasource and annotation operations requires the matching action and scope.

## Telemetry

The randomized OTLP route and Grafana service-account token are stored in Google
Secret Manager. Cloud Run receives them through secret/environment bindings;
neither appears in source or the public acceptance artifact.

Prometheus scrapes Cloud Run `/metrics`. Cloud Run exports structured logs and
spans over OTLP/HTTP to Alloy, which forwards them to Loki and Tempo. The public
health endpoint calls Gemini and executes a real MCP PromQL query; configuration
presence alone cannot produce a passing health result.

## Acceptance evidence

Record a redacted JSON artifact containing:

1. advertised official MCP server name/version;
2. advertised tool names used in the demo;
3. one PromQL read, one LogQL read, and one trace read;
4. annotation ID and incident/alert-rule ID created by the approved action;
5. the before/after deterministic gate result;
6. no token, basic-auth value, OTLP header, or private log payload.

Official references:

- <https://github.com/grafana/mcp-grafana>
- <https://github.com/grafana/mcp-grafana/releases/tag/v1.1.0>
- <https://grafana.com/docs/grafana-cloud/machine-learning/mcp/>
