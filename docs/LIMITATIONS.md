# Limitations

Stated here and on the product surface, so a judge finds them before they find
them for themselves.

## What is simulated

- **The delivery receiver is simulated.** Ingest, FFmpeg transcoding, QC,
  packaging, failures, durations, retries, metrics, logs and traces are real
  measurements from real subprocess execution. The final handoff to a
  distributor is not.
- **The engineering source is generated.** A three-second `lavfi` pattern with a
  sine tone proves the pipeline; it does not prove feature-length performance,
  and no timing here should be read as a production encode benchmark.

## What the numbers do and do not support

- **Five classifier cases is engineering evidence, not a statistical claim.** The
  classifier recovers the failure class from FFmpeg's own stderr, exit status,
  output size and QC result, and it cannot read the injected scenario, and a test
  asserts that. That makes the result non-circular. It does not make it a
  population-level accuracy measurement.
- **The gate fixtures are constructed.** The schedule histories in
  `benchmark/latest.json` under `gate_evaluation` are hand-built to exercise gate
  behaviour: one blip must not open an incident, a sustained burn must. They are
  labelled as fixtures and are not production telemetry.
- **Lead time is a projection, not an observation.** `measured_lead_time` takes
  the p95 measured from the run's real FFmpeg jobs and projects it onto a stated
  delivery size and contract window. The per-spec cost is measured; the delivery
  size and window are assumptions.
- **The duration history is sparse.** A production p95 needs many more jobs
  grouped by codec and spec class than this build has run.
- **Gemini's corroboration quality is not reduced to a number.** The agents are
  assessed by inspection of deployed runs, not by a score we would have to
  defend as a benchmark.

## Scope of the deterministic classifier

- It recognises four classes plus an explicit `transcode_failure` for anything it
  does not recognise. That unclassified outcome is an honest "we do not know",
  and the evaluation counts it as a miss rather than letting a default guess
  score as correct.
- Capacity starvation is **not** implemented. A queue-depth-driven class would
  need a real worker pool under contention, which this build does not have.
- Signatures are matched against FFmpeg's English stderr. A differently localised
  or substantially different FFmpeg build could fall through to unclassified.

## Infrastructure

- The stack is **self-hosted Grafana OSS**, not Grafana Cloud. The contest rules
  permit the open-source MCP server with a service-account token for unattended
  deployments, which is what this is. Grafana Cloud-only capabilities, namely the SLO
  app, IRM, Sift and OnCall, are therefore unavailable and are not used or implied.
- **AI Observability wording.** SLATE emits OpenTelemetry `gen_ai.*` spans and
  Prometheus counters for per-agent token usage, operation duration and MCP tool
  activity, and reads them back through the official Grafana MCP server. These
  are the conventions Grafana Cloud AI Observability consumes, but that Cloud
  product is not configured here and no part of this build depends on it.
- Grafana anonymous access is Viewer-only over generated contest data.
- Grafana MCP and OTLP export fail closed when credentials are absent rather than
  degrading to a local guess.

## Product scope

- This is a judging environment, not a delivery control plane. Before it touched
  studio systems it would need identity-aware operator auth, per-tenant
  authorization, rate limits, audit retention and private ingress.
- No agent can create jeopardy, change a contractual date, or execute a
  remediation. An operator may only approve an option the agent actually
  proposed; the API refuses anything else with HTTP 409.
- Predictive pre-miss alerting and schedule-budget thinking have prior art. See
  `PRIOR-ART.md`. This project does not claim conceptual novelty.
