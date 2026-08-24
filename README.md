# SLATE

SLATE treats a contractual media-delivery date as a deterministic schedule budget. A real FFmpeg pipeline fans a self-generated source into actual rendition jobs, performs real conformance checks, packages the outputs, and sends them to an explicitly simulated delivery endpoint. Real durations, failures, queue depth, bytes, logs, and traces become the observability data; no demo metric is pre-scripted.

Judging deployment (Cloud Run and Vertex AI, `us-central1`): <https://slate-delivery-slo-109051079423.us-central1.run.app>

Live Grafana control tower: <https://35-255-68-247.sslip.io/d/slate-delivery/slate-delivery-control-tower?kiosk>

Start with [`JUDGING.md`](JUDGING.md) and the machine-readable
[`submission-evidence.json`](submission-evidence.json).

The schedule-budget mechanic and predictive pre-miss alerting are not novel. Our documented search found standard pipeline observability, automated QC, predictive logistics alerts, and writing applying error-budget thinking to delivery. We have not confirmed whether SDVI Rally, Dalet Flex, Vidispine, or Ateme predict contractual deadline risk, and do not claim they cannot.

## Deterministic boundary

An incident is at risk only when all three rules pass:

1. projected completion is after the contractual date;
2. schedule burn is positive across at least two consecutive evaluation windows of at least five seconds each;
3. work remains.

Gemini cannot compute or override this verdict. Watch, Diagnose, and Remediate agents use Grafana exclusively through the official MCP path. Remediate proposes only. An operator must approve every execution.

## Verified baseline

- `21 passed` locally, plus two FFmpeg-dependent tests that run when FFmpeg is present. The deployed container includes FFmpeg.
- Hosted Cloud Run acceptance: real transcode passed, package completed, 127,826 output bytes.
- Four-fault engineering benchmark: 4/4 deterministic labels correct.
- Constructed schedule-history benchmark: sustained case detected six hours ahead; 0/2 negative fixtures opened jeopardy.

These are small engineering fixtures, not statistical proof. The exact report, its provenance, and its limitations are in `benchmark/latest.json`.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt pytest httpx
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn slate_app.main:app --reload
```

FFmpeg is mandatory. FFprobe is preferred; when it is unavailable, SLATE decodes the actual output with FFmpeg and parses the selected stream. It never substitutes requested codec/dimensions or simulated timings.

## Current build status

- Real ingest, parallel FFmpeg transcodes, output QC, packaging, and a simulated delivery receiver.
- Real Prometheus metrics plus OTLP logs and traces, ingested by a dedicated self-hosted Grafana OSS stack (Grafana, Prometheus, Loki, Tempo, and Alloy).
- PromQL recording rule and sustained jeopardy alert.
- Three-role Google ADK topology invoked at runtime through `POST /v1/jeopardy/{id}/investigate`; each role's output is separately inspectable.
- Official `grafana/mcp-grafana` v1.1.0 runtime; health is based on a live MCP PromQL round-trip, not environment presence.
- Public API: `/v1/deliveries`, `/v1/jeopardy/{id}`, deterministic-gated agent investigation, remediation approval, `/metrics`, and judge-visible Grafana evidence.
- Durable production state in Firestore; local development deliberately uses in-memory state.
- Light-default delivery board with page-level Plain/Technical modes and a one-click real judge proof.

The required Grafana runtime integration is live and verified: official MCP tool discovery, PromQL and LogQL reads, an MCP-created annotation after human approval, and a completed three-agent ADK investigation all passed on 20 August 2026. The rules explicitly allow the open-source Grafana MCP server with a service-account token for unattended deployments. Browser-based visual sign-off and the public three-minute video remain release tasks.
