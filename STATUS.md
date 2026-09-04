# SLATE implementation status

Updated: 2026-09-02. Live revision `slate-delivery-slo-00027-4zz`, `min-instances 1`.

## Complete

- [x] Independent public repository and detected Apache-2.0 license
- [x] Real FFmpeg ingest, parallel rendition fan-out, QC against a configurable rule set, and packaging
- [x] Honest simulated receiver boundary, stated on the product surface
- [x] Deterministic three-threshold jeopardy gate, unit-tested, thresholds rendered in UI and API
- [x] **Deterministic failure classification from observed output only** (`slate_app/classify.py`):
      FFmpeg stderr, exit status, output bytes and QC result. The injected scenario now only
      configures reality — an unreadable file, a missing encoder, a real deadline, an extra
      conformance rule — and is unreadable from the measurement path
- [x] Guard tests: the classifier source may not contain `fault_mode`, nor may `_transcode`,
      `_attempt`, `_qc` or `run`, and no emitted job result may contain the scenario name
- [x] Real retries, bounded and only for genuinely transient classes
- [x] Human approval on every remediation endpoint; no auto-action path exists in code
- [x] **Closed remediation loop**: Remediate emits a typed `RemediationPlan` constrained to the
      four actions the API can perform, the board renders those as the approval controls, the
      endpoint returns 409 for anything the agent did not propose, and an approved
      `requeue_safe` plus a re-run returns the delivery to `recovered`
- [x] Prometheus metrics, structured logs and OpenTelemetry spans
- [x] Google ADK Watch / Diagnose / Remediate topology with a real runtime request path
- [x] Dedicated self-hosted Grafana OSS stack on GCP with HTTPS, now including the image renderer
- [x] Live Prometheus scrape plus OTLP Loki/Tempo ingestion
- [x] Official `grafana/mcp-grafana` v1.1.0; health is a live MCP PromQL round-trip
- [x] **Loki evidence actually reaches the agents.** The bound LogQL returned zero rows on every
      previous run — including in the recorded acceptance artifact — because the OTLP body is a
      JSON string nested inside `body`. Reparsing after `line_format` returns the real events,
      and Diagnose now quotes FFmpeg's own stderr
- [x] **MCP alert-rule write**: a Grafana-managed rule provisioned per delivery at creation via
      `alerting_manage_rules`, verified through the provisioning API
- [x] MCP annotation write, after and only after human approval
- [x] **MCP panel rendering read multimodally**: `get_panel_image` renders the schedule-budget
      panel, Gemini describes the chart, and the PNG it was given is shown beside the reading
- [x] Evidence sweep runs over one MCP session instead of one subprocess per query
- [x] Firestore production state; fail-closed live readiness probe
- [x] Gemini/ADK calls instrumented with OpenTelemetry `gen_ai.*` spans and Prometheus counters,
      read back through the official MCP server at `/v1/integrations/grafana/ai-observability`
- [x] Per-delivery Markdown report a supervisor could forward
- [x] Delete route that removes a delivery and its provisioned alert rule
- [x] Board: schedule-budget burn-down per title with the contract as the zero line, tightest
      budget across the fleet, observed classes, retries, QC rules, decisions
- [x] Light-default board with Plain/Technical modes and an opt-in remembered dark theme
- [x] Five-scenario classifier evaluation against ground truth it cannot see, including a
      healthy control; unrecognised failures counted as misses rather than defaulted
- [x] Lead time derived from a measured p95 and labelled as a projection
- [x] `docs/PRIOR-ART.md` naming the incumbents and conceding the mechanic
- [x] Board seeded with three contracted titles; stale duplicate judge-proof records and their
      alert rules removed
- [x] 48 tests pass locally; the 9 FFmpeg-dependent proofs run in CI, where
      `SLATE_REQUIRE_FULL_SUITE=1` makes a skip a failure so a broken FFmpeg
      install cannot leave the badge green over proofs that never executed
- [x] `scripts/mutation_check.py` breaks the classifier six ways in CI and fails
      if a guard does not notice. It found one guard that blanked every string
      constant before checking, so `getattr(record, "fault_mode")` passed
      straight through it — the guard reported success with the leak present

## Release tasks

- [ ] Record and publish the under-three-minute demo — script in `docs/DEMO-SCRIPT.md`
- [ ] Complete the Devpost submission — paste-ready copy in `docs/DEVPOST.md`
- [ ] Obtain review from a streaming or broadcast operations professional before making any
      stronger claim about operational fit (not obtained)

## Deliberately not done

- **Capacity starvation** as a failure class. It would need a real worker pool under
  contention; classifying it without one would be the same fiction this build just removed.
- **Grafana Cloud features** — the SLO app, IRM, Sift, OnCall. The stack is self-hosted OSS,
  which the rules permit for unattended deployments, so those are unavailable and unused.
- **A score for Gemini's corroboration quality.** Assessed by inspection of deployed runs
  rather than reduced to a number this build could not defend.
