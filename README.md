# SLATE

SLATE treats a contractual media-delivery date as a deterministic schedule budget. A real FFmpeg pipeline fans a self-generated source into actual rendition jobs, performs real conformance checks, packages the outputs, and sends them to an explicitly simulated delivery endpoint. Real durations, failures, queue depth, bytes, logs, and traces become the observability data; no demo metric is pre-scripted.

Judging deployment (Cloud Run and Vertex AI, `us-central1`): <https://slate-delivery-slo-109051079423.us-central1.run.app>

Live Grafana control tower: <https://35-255-68-247.sslip.io/d/slate-delivery-slo/slate-c2b7-contractual-delivery-slo?kiosk>

Start with [`JUDGING.md`](JUDGING.md) and the machine-readable
[`submission-evidence.json`](submission-evidence.json).

The schedule-budget mechanic and predictive pre-miss alerting are not novel. Our documented search found standard pipeline observability, automated QC, predictive logistics alerts, and writing applying error-budget thinking to delivery. We have not confirmed whether SDVI Rally, Dalet Flex, Vidispine, or Ateme predict contractual deadline risk, and do not claim they cannot. See [`docs/PRIOR-ART.md`](docs/PRIOR-ART.md).

## Two decisions the model cannot make

**Is this delivery in jeopardy?** A pure function decides. An incident opens only when all three are true:

1. projected completion is after the contractual date;
2. schedule burn is positive across at least two consecutive evaluation windows of at least five seconds each;
3. work remains.

**Why did the rendition fail?** A deterministic classifier decides, from FFmpeg's own stderr, exit status, output size and QC result, in [`slate_app/classify.py`](slate_app/classify.py).

That second one used to be false. An earlier build labelled each failure with the fault that had been *injected* into the run, wrote that label onto the trace span and the Prometheus counter, and then asked the agent to "diagnose" it. The agent read the answer key back, and the benchmark scored the round trip at 100%. The scenario now only configures reality: an unreadable file, a missing encoder, a real deadline, an extra conformance rule. The class has to be recovered from what FFmpeg actually printed. Two tests enforce it: the classifier's source may not contain `fault_mode`, and neither may the measurement path.

Gemini corroborates both decisions against raw evidence and proposes bounded options. Watch, Diagnose and Remediate use Grafana exclusively through the official MCP path. Remediate proposes only, in a typed schema constrained to the four actions the API can actually perform, and the approval endpoint refuses any action the agent did not propose.

## What runs through the official Grafana MCP server

| Operation | Tool | Where |
|---|---|---|
| Metrics | `query_prometheus` | Agent evidence, health probe, AI-observability read-back |
| Logs | `query_loki_logs` | Agent evidence, the real FFmpeg stderr |
| Traces | `tempo_get-trace` | Agent evidence, per-delivery span tree |
| **Dashboard search** | `search_dashboards` | `/v1/integrations/grafana/dashboards` finds the operator's dashboard and returns a link back to Grafana for human review |
| **Alert rule write** | `alerting_manage_rules` | A Grafana-managed rule provisioned per delivery at creation |
| **Annotation write** | `create_annotation` | After, and only after, a human approves a remediation |
| **Panel render** | `get_panel_image` | Grafana draws the schedule-budget panel, MCP carries the PNG, Gemini reads the chart multimodally at `/v1/integrations/grafana/panel-reading` |

### Three of those seven are not the obvious use

The first four are what anyone would do with observability MCP. These three are the reason this
integration is worth a look:

- **`alerting_manage_rules`.** Alert rules are normally authored once by a human and left alone.
  SLATE writes one **per delivery** at creation, because the thing being watched is a contract and
  every contract has a different date. The rule is deleted with the delivery.
- **`create_annotation`.** The write is not the agent acting. It fires only after a human approves
  a remediation, so the Grafana timeline becomes the audit record of who decided what, and when.
- **`get_panel_image`.** MCP is treated as a text API almost everywhere. Here Grafana renders the
  same panel the supervisor is looking at, MCP carries the PNG back, and Gemini reads the *chart*
  multimodally. The PNG it was given is shown beside the reading so you can check one against the
  other.

### Coverage against what the track requirement actually names

`/v1/integrations/grafana/inventory` returns the requirement's capability list in the
requirement's own wording, each row mapped to the tool that answers it, and the product page
renders it. **Seven of the eight are covered.** The eighth, investigating incidents through IRM,
is a Grafana Cloud plugin: the rules direct unattended deployments to the self-hosted OSS server,
and that choice is what removes it. `tests/test_grafana_mcp.py` fails the build if a row claims
"covered" while naming a tool SLATE does not call.

This server advertises **72 tools**; SLATE calls seven. `/v1/integrations/grafana/evidence`
lists each one with what it is for and confirms the server offers it, alongside the capabilities
named in the track requirement that SLATE **declines** and why: Grafana IRM incidents, OnCall
and Sift are Grafana Cloud plugins unavailable on a self-hosted OSS stack, and `update_dashboard`
is refused on purpose so the operator's view is not something the model can rewrite.

The agents' own OpenTelemetry `gen_ai.*` token, latency and MCP-tool series are read back through the same MCP server at `/v1/integrations/grafana/ai-observability`. These are the conventions Grafana Cloud AI Observability consumes; that Cloud product is not configured here and nothing depends on it.

## What a failure alert cannot see

This is the claim, and it is measured rather than argued. Eight heavy renditions at a measured
five seconds each is forty seconds of work. Give the delivery a fifty second window and encode
it in waves, with **no fault injected at all**:

| | wave 1 | wave 2 | wave 3 |
|---|---|---|---|
| failures | 0 | 0 | 0 |
| still to encode | 7 | 6 | 5 |
| measured work left | 34.8s | 33.8s | 28.1s |
| window left | 43.3s | 31.1s | 19.9s |
| verdict | healthy | healthy | **at_risk** |

Every rendition passed. On that same run, `/v1/evaluation/detectors` reports:

- `any_failure`: **silent**. Nothing failed, so it has nothing to say, and it will stay silent
  until the date goes by.
- `deadline_passed`: **silent**. Correct, and useless.
- `slate_gate`: **fires, 19.7 seconds before the contractual date.**

The button on the page runs exactly that, live, in about thirty seconds.

What this does *not* show, and the page says so: SLATE does not beat a failure alert to a hard
failure. A failure is instant and nothing beats it. It shows the failure alert is answering a
different question, and that a delivery can be lost without anything failing.

The converse is checked too. A rendition that fails with two days of slack is a `cried_wolf`
case: the ordinary alert fires, SLATE stays quiet, because the date is not at risk.

## Not a fixed demo path

Three things a judge can drive that are not our fixtures:

- **Named preset scenarios** at `/v1/presets`: a healthy four-rendition ladder, a festival cut
  whose encoder is missing, and a distributor tightening the QC spec mid-delivery. Each one
  loads in a click, downloads as JSON, and is *exactly* the body `POST /v1/deliveries` accepts.
  A test asserts that: the downloaded file posted back unchanged creates the same record, so a
  preset is not a privileged path.
- **Your own delivery ladder.** The rendition rows on the page are not decoration. Resolution,
  codec and bitrate are passed to FFmpeg unchanged, and the QC stage decodes what actually came
  back rather than trusting what was requested. Out-of-range specs are refused with a 422, not
  silently clamped.
- **Your own PromQL** at `/v1/analyze/promql`, run through the same official Grafana MCP server
  the agents use, returning the server's raw response. The agents run three fixed queries on
  purpose, because an agent free to compose any query can also compose a misleading one, and that is a
  limit on the agent, not on the integration.

## Verified baseline

- `70 passed, 9 skipped` locally; the nine are FFmpeg-dependent and run in CI, which installs FFmpeg. The deployed container includes FFmpeg.
- `scripts/check_page.py` loads the page in a headless browser and asserts the DOM only
  JavaScript can build. It has caught a page-dead defect twice that no unit test would have.
- `scripts/seed_board.py` resets the board to three healthy titles with fresh contractual dates.
  Absolute dates go stale; run it before recording or before a judging window.
- Five-scenario classifier evaluation against ground truth the classifier cannot see, including a healthy control that a label-everything classifier would fail.
- Hosted Cloud Run acceptance: real transcode, package, and simulated delivery.
- Constructed schedule-history fixtures prove one blip does not open an incident and a sustained burn does.

These are small engineering fixtures, not statistical proof. Provenance and limits are in [`benchmark/latest.json`](benchmark/latest.json) and [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md).

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt pytest httpx
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn slate_app.main:app --reload
```

FFmpeg is mandatory. FFprobe is preferred; when it is unavailable, SLATE decodes the actual output with FFmpeg and parses the selected stream. It never substitutes requested codec/dimensions or simulated timings.

## Current build status

- Real ingest, parallel FFmpeg transcodes, output QC against a configurable rule set, packaging, and a simulated delivery receiver.
- Deterministic failure classification from observed output, with bounded retries only for genuinely transient classes.
- Real Prometheus metrics plus OTLP logs and traces, ingested by a dedicated self-hosted Grafana OSS stack (Grafana, Prometheus, Loki, Tempo, Alloy, and the image renderer).
- PromQL recording rule and sustained jeopardy alert, plus a per-delivery Grafana-managed alert rule written through MCP.
- Three-role Google ADK topology invoked at runtime through `POST /v1/jeopardy/{id}/investigate`; each role's output is separately inspectable, and the evidence sweep runs over one MCP session instead of one subprocess per query.
- Closed remediation loop: Remediate proposes typed options, the board renders them as approval controls, approval executes and annotates, and a requeue that clears the fault returns the delivery to `recovered`.
- Public API: `/v1/deliveries`, `/v1/jeopardy/{id}`, agent investigation, remediation approval, per-delivery Markdown report, delete, `/metrics`, and judge-visible Grafana evidence.
- Durable production state in Firestore; local development deliberately uses in-memory state.
- Light-default delivery board with schedule-budget burn-down per title, page-level Plain/Technical modes, an opt-in dark theme, and a one-click real judge proof.

The required Grafana runtime integration is live and verified: official MCP tool discovery, PromQL, LogQL and Tempo reads, an MCP-created alert rule at delivery creation, an MCP-created annotation after human approval, MCP panel rendering read multimodally by Gemini, and a completed three-agent ADK investigation. The rules explicitly allow the open-source Grafana MCP server with a service-account token for unattended deployments. The public three-minute video remains a release task.
