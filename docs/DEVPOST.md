# Devpost submission text

Paste-ready copy for each required field. Track: **Grafana**.

---

## Elevator pitch (200 char limit)

A delivery date you cannot move is an SLO. SLATE burns it down in real time from a real FFmpeg pipeline, and reads it back through Grafana MCP.

---

## Inspiration

Every facility delivering to a streamer runs the same gauntlet: ingest, transcode to N
deliverable specs, QC, package, deliver, against a contractual date. QC rejection at the
platform submission stage is dramatically more expensive than catching the same fault locally,
and an unexpected rejection can take a launch date with it.

The standard mitigation is to move the quality gate earlier. That is right, and it works. But
it answers "is this file correct", not "does the remaining work still fit before the date". So
facilities discover they are going to miss when they miss.

In SRE, that second question already has an answer: an error budget, and a burn-rate alert that
fires while you can still act. Apply it literally, with the deadline as the hard constraint and
*schedule* as the resource being burned:

```
delivery_window   = contractual_date - now
work_remaining    = Σ(pending specs × measured p95 per spec)
schedule_budget   = delivery_window - work_remaining
```

**None of that reframe is ours.** Logistics platforms already forecast completion against an SLA
window and alert before a breach, and applying error-budget thinking to delivery has published
prior art. What we could not find documented was this pattern applied to a media deliverable
pipeline with per-spec rendition fan-out, where the failure unit is one transcode and the
consequence is a contractual rejection. `docs/PRIOR-ART.md` names the incumbents and says
plainly what we did not confirm.

## What it does

SLATE runs a **real** pipeline: FFmpeg ingest, parallel rendition fan-out, conformance QC
and packaging. It turns its real durations, failures, retries and queue depth into the telemetry
that drives a deterministic jeopardy gate. An incident opens only when three things are true at
once: projected completion is past the contractual date, burn has been positive across two
consecutive evaluation windows, and work remains. One bad window is not evidence.

When the gate opens, three Google ADK agents on Gemini investigate through the official Grafana
MCP server, and a supervisor approves a costed option. Nothing else can act.

## The bug that mattered most

An earlier build of SLATE labelled every failure with the fault that had been *injected* into
the run. That label went onto the trace span and into the Prometheus `failure_class` counter,
and then the agent was asked to "diagnose" it. It read the answer key back and the benchmark
scored the round trip at 100%.

That number was measuring nothing, and we removed it.

The injected scenario now only configures **reality**: a genuinely unreadable file on disk, an
encoder name this FFmpeg build does not have, a real subprocess deadline, an additional
conformance rule the asset cannot satisfy. The class has to be recovered from what FFmpeg
actually printed, from stderr signatures, exit status, output size and QC result, by a classifier in
`slate_app/classify.py` that structurally cannot see the scenario.

Three tests enforce it, and they fail the build:

- the classifier's own source may not contain `fault_mode`;
- neither may `_transcode`, `_attempt`, `_qc` or `run`. Only `plan` may, and it builds the real
  configuration, is allowed to read it;
- no emitted job result may contain the scenario name.

An unrecognised failure is reported as `transcode_failure`, an honest "we do not know", and the
evaluation counts it as a miss rather than letting a default guess score as correct. The
evaluation includes a healthy control, which a classifier that labels everything would fail.

## The other bug: the agents had no logs at all

The LogQL bound to the agents was `{service_name="slate"} | json | delivery_id="..."`. It
returned zero rows on every run, including in our own recorded acceptance artifact, because
OTLP delivers the log line as a JSON *string* nested inside `body`, so one `| json` stage
exposes `body` and never `delivery_id`. The agents appeared to be querying logs and were
receiving nothing.

Reparsing after `line_format` fixed it, and it is why Diagnose can now quote FFmpeg's actual
stderr, `Unknown encoder 'encoder_that_does_not_exist'`, instead of restating a label.

## How it uses the Grafana stack

Everything the agents read, and every Grafana write, goes through the official
`grafana/mcp-grafana` v1.1.0 server over stdio, against a dedicated self-hosted Grafana OSS
stack. The rules explicitly permit the open-source server with a service-account token for
unattended deployments, which is what this is.

| Operation | Tool | Where it happens |
|---|---|---|
| Metrics | `query_prometheus` | Agent evidence, health probe, agent-cost read-back |
| Logs | `query_loki_logs` | Agent evidence, the real FFmpeg stderr |
| Traces | `tempo_get-trace` | Per-delivery span tree: ingest → each rendition → QC → package |
| **Alert rule write** | `alerting_manage_rules` | A Grafana-managed rule provisioned **per delivery**, at creation |
| **Annotation write** | `create_annotation` | Only after a human approves a remediation |
| **Panel render** | `get_panel_image` | Grafana draws the schedule-budget panel, MCP carries the PNG, Gemini reads the chart |

The product page states this coverage rather than leaving it to be inferred, and states it
accurately: **this server advertises 72 tools and SLATE calls seven.** Each row is confirmed
advertised against the running server when the page loads, so the status is earned rather than
asserted. The page also renders the requirement's capability list line by line, in the requirement's own
wording: querying metrics, logs and traces, searching dashboards, managing alerts, correlating
all three during root-cause analysis, and AI Observability. SLATE answers seven of the eight.
The eighth, investigating incidents, runs on Grafana IRM, a Grafana Cloud plugin this self-hosted OSS stack does not have; that is
listed on the page as a decline with the reason, next to OnCall, Sift, and `update_dashboard`,
which is refused on purpose so the operator's view is not something the model can rewrite.

That last one is the loop closing on itself: the agent's operational sense is the same picture
the supervisor is looking at, read as an image rather than as numbers it was handed. The PNG is
shown beside the reading so a viewer can check one against the other. The reading is explicitly
commentary, and `decision_source` stays `deterministic_gate`.

The alert rule is authored by SLATE, not by Gemini. A model that cannot set the verdict must not
be able to author the rule that encodes it either.

## Watching the watcher

SLATE's agents watch the pipeline; nothing was watching the agents. They now emit OpenTelemetry
`gen_ai.*` spans and Prometheus counters for per-agent token usage, operation duration and MCP
tool activity, and `/v1/integrations/grafana/ai-observability` asks **the same MCP server** what
the agents cost. These are the conventions Grafana Cloud AI Observability consumes; that Cloud
product is not configured here and nothing depends on it.

## The decision boundary

| Layer | Owns | Cannot |
|---|---|---|
| Pure function (`gate.py`) | Whether the delivery is in jeopardy | none |
| Pure function (`classify.py`) | Why the rendition failed | See the injected scenario |
| Gemini via ADK | Corroborating both against evidence; proposing typed options; describing a rendered chart | Set a verdict, assign a class, execute anything, author an alert rule |
| Delivery supervisor | Every action | none |

Remediate emits a typed `RemediationPlan` constrained to the four actions the API can actually
perform, each with an honest schedule cost and a reversibility flag. The board renders those
options as the approval buttons themselves, and the endpoint returns **409** for any action the
agent did not propose, so the reasoning and the control are the same object, not two things
sitting next to each other. Approving `requeue_safe` and re-running returns the delivery to
`recovered`.

## Technologies and data

Cloud Run, Vertex AI Gemini 2.5 Flash, Google ADK, Firestore, Secret Manager, official
`grafana/mcp-grafana` v1.1.0, Grafana OSS 12.1 with Prometheus, Loki, Tempo, Alloy and the
image renderer on a dedicated GCP VM behind Caddy, OpenTelemetry, FFmpeg, FastAPI, Pydantic.

All media is generated at runtime by FFmpeg from a `lavfi` test pattern and a sine tone. There
is no third-party footage, music, logo or found dataset anywhere in the product or the demo.

## Findings and learnings

- **A benchmark can measure its own setup.** Ours did, at 100%, for weeks. The tell was that the
  "diagnosis" never disagreed with anything. Separating *what configures the run* from *what
  observes it* was the single highest-value change in the project, and it is now enforced by
  tests rather than by discipline.
- **A query that returns nothing looks exactly like a query that returns nothing interesting.**
  The dead LogQL survived because empty results were reported honestly, so nothing looked
  broken. Assert on the shape of evidence, not just on the absence of errors.
- **AI observability is not agency.** Watching an agent is not the same as giving it a job.
  The useful pattern was an agent that reads the same correlated telemetry an operator trusts,
  through the partner's own server, and then has to ask.
- **Honest uncertainty needs somewhere to go.** Adding an explicit unclassified outcome, counted
  as a miss, was what made the accuracy number worth printing.

## What's next

Capacity starvation as a real class, which needs a worker pool under genuine contention rather
than a fabricated label. More runs for a defensible p95 by codec and spec class. Review by a
streaming or broadcast operations professional. We have not had one, and `docs/LIMITATIONS.md`
says so alongside everything else we have not shown.

## Built with

`google-adk` · `google-genai` · Gemini 2.5 Flash · Vertex AI · Cloud Run · Firestore · Secret
Manager · `grafana/mcp-grafana` (official MCP server) · Grafana OSS · Prometheus · Loki · Tempo ·
Alloy · Grafana Image Renderer · Model Context Protocol · OpenTelemetry · FFmpeg · FastAPI ·
Pydantic · Caddy · Docker · GitHub Actions

## Try it out

- Hosted app: https://slate-delivery-slo-109051079423.us-central1.run.app
- Grafana control tower: https://35-255-68-247.sslip.io/d/slate-delivery-slo/slate-c2b7-contractual-delivery-slo?kiosk
- Repository: https://github.com/usv240/slate
- Shortest judge path: [`JUDGING.md`](https://github.com/usv240/slate/blob/main/JUDGING.md)
- What we have not shown: [`docs/LIMITATIONS.md`](https://github.com/usv240/slate/blob/main/docs/LIMITATIONS.md)
- Prior art, named: [`docs/PRIOR-ART.md`](https://github.com/usv240/slate/blob/main/docs/PRIOR-ART.md)

---

## Field-by-field checklist

- [ ] Partner track selected: **Grafana**
- [ ] Hosted project URL
- [ ] Public repository URL
- [ ] Public video URL (YouTube/Vimeo, ≤3:00, English or subtitled)
- [ ] Text description (features, functionality, technologies, data sources, findings and
      learnings), all covered above
- [ ] Team members added on Devpost
- [ ] Every link opened signed out and confirmed working
- [ ] Repo license shows Apache-2.0 in the About section
- [ ] Submitted before **2026-09-09, 2:00 PM PT**
