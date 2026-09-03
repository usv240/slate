# Judge path

## Stage-one viability

- Track: **Grafana**.
- Public product: <https://slate-delivery-slo-109051079423.us-central1.run.app>
- Grafana control tower: <https://35-255-68-247.sslip.io/d/slate-delivery-slo/slate-c2b7-contractual-delivery-slo?kiosk>
- Repository and detected Apache-2.0 licence: <https://github.com/usv240/slate>
- Google runtime: `/health` performs a real Vertex AI generation with Gemini 2.5 Flash;
  `POST /v1/jeopardy/{id}/investigate` runs a Google ADK `SequentialAgent` of three
  `LlmAgent`s on Vertex.
- Mandatory partner runtime: every operational observation and every Grafana write goes
  through the official `grafana/mcp-grafana` v1.1.0 server over stdio against a dedicated
  self-hosted Grafana OSS stack. The rules explicitly permit the open-source server with a
  service-account token for unattended deployments.
- The delivery receiver is explicitly simulated. Everything upstream of it is real execution.
- The public video and the Devpost form remain release actions and are not represented as done.

## Three-minute test

1. Open `/`. Three contracted titles, day-scale dates, all green. Each shows the schedule
   budget the deterministic gate computed and whether its Grafana alert rule was provisioned.
2. Press **Run 20s judge proof**. It creates a delivery whose encoder does not exist, then
   runs the real FFmpeg pipeline three times. Watch the gate refuse to open an incident on the
   first two windows — one blip is not evidence — and open on the third.
3. The investigation renders automatically. Check four things:
   - `decision_source` is `deterministic_gate` and `classification_source` is
     `deterministic_stderr_classifier`;
   - the PromQL, LogQL and Tempo rows are the queries the agents were actually bound to;
   - **Diagnose quotes FFmpeg's own stderr** — `Unknown encoder 'encoder_that_does_not_exist'`
     — rather than restating a label;
   - Remediate's options are typed, costed, and rendered as the approval buttons themselves.
4. Approve the recommended option. A Grafana annotation is written only at that moment. Press
   **Run real pipeline** once more: the delivery returns to `recovered` and the simulated
   receiver accepts it.
5. Press **Render the panel through MCP**. Grafana draws the schedule-budget panel, MCP carries
   the PNG back, and Gemini describes the chart. The PNG it was given is shown beside the
   reading so you can check one against the other.
6. Open `/health`; all five runtime checks should be true.

## The claim we most expect to be tested

**"Your agent is just reading back the fault you injected."** It was. An earlier build wrote
the injected scenario onto the trace span and derived the Prometheus `failure_class` label from
it, then asked Gemini to diagnose it. The benchmark scored that round trip at 100%.

Now the scenario only configures reality — an unreadable file on disk, an encoder name this
FFmpeg build does not have, a real subprocess deadline, an additional conformance rule — and the
class must be recovered from what FFmpeg actually printed.

| Check it here | What it shows |
|---|---|
| `slate_app/classify.py` | The whole classifier. Signatures over stderr, exit status, output size and QC result |
| `tests/test_classify.py` | Asserts the classifier's own source contains no `fault_mode`, and neither does the measurement path |
| `tests/test_pipeline.py` | Runs all five scenarios through real FFmpeg and asserts the recovered class; asserts no emitted result contains the scenario name |
| `benchmark/latest.json` | Five scenarios including a healthy control a label-everything classifier would fail; unrecognised failures are reported as `transcode_failure` and counted as misses |

## Verifying the rest is not theatre

| Claim | Check it here |
|---|---|
| The gate is computed, not asserted | `slate_app/gate.py` is a pure function; `/v1/jeopardy/{id}` returns `gate.passed` and `gate.failed` with observed values and required thresholds |
| One blip cannot open an incident | `tests/test_gate.py`; and the judge proof visibly stays healthy for two windows |
| The model cannot act | Remediate has `output_schema` and no tools; the approval endpoint returns **409** for any action the agent did not propose |
| The agent really used MCP | `/v1/integrations/grafana/evidence` lists advertised tools and runs a live query; every tool call is a span and a Prometheus counter |
| MCP writes are real | The per-delivery alert rule is readable at `/api/v1/provisioning/alert-rules/{uid}` on the Grafana stack; annotations appear on the dashboard |
| The agent's own cost is observable | `/v1/integrations/grafana/ai-observability` reads the `gen_ai.*` token, latency and MCP-tool series back through the same MCP server |
| It fails closed | Remove the Grafana credentials and every integration route returns 503 rather than a local guess |

## Four equal judging criteria

| Criterion | Inspect this | What it proves |
|---|---|---|
| Technological Implementation | The judge proof end to end, then `slate_app/classify.py` and the MCP write surface | A real FFmpeg pipeline, a deterministic gate and a deterministic classifier that cannot see the answer, three ADK roles bound to one MCP session, and MCP used for reads, alert-rule writes, annotations and panel rendering |
| Design | The board in Plain and Technical, light and dark | One operator path from risk to evidence to a costed proposal to approval to recovery, with a burn-down per title and a report a supervisor could forward |
| Potential Impact | The three-window judge proof and `docs/LIMITATIONS.md` | Contractual jeopardy is visible before a binary deadline miss. The receiver is simulated and the lead-time figure is a projection; both are stated |
| Quality of the Idea | `docs/PRIOR-ART.md`, then the panel-reading section | The mechanic is conceded as commodity and the incumbents are named. What is unusual is the partner use: a media deliverable as a Tempo trace, alert rules authored per delivery through MCP, and Grafana's own renderer closing a multimodal loop |

No agent can create jeopardy, change a contractual date, or execute a remediation. Benchmark
fixtures are small engineering evidence, not a production SLO study.
