# SLATE implementation status

Updated: 2026-09-04. Live revision `slate-delivery-slo-00034-tx8`, `min-instances 1`.

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

- [x] **Not a fixed demo path**: three named preset scenarios that load in a click and download
      as JSON, a custom rendition-ladder builder whose rows become the real FFmpeg arguments,
      and `/v1/analyze/promql` for a judge's own query through the official MCP server
- [x] Optional stateless judge keys raising the allowance on the two endpoints that spend Gemini
      tokens; reads uncapped, abstentions free, a bad key falls back to anonymous
- [x] Demo-video slot that is honest when empty and becomes a nocookie embed via
      `SLATE_DEMO_VIDEO_URL`
- [x] `scripts/check_page.py` loads the page in a headless browser and asserts the DOM only
      JavaScript can build. **It found the page rendering nothing at all — twice — while the
      whole suite was green.** A syntax error in one string literal had detached every listener
- [x] `scripts/seed_board.py` resets the board to three healthy titles with fresh contractual
      dates, because absolute dates go stale between a seeding and a recording

- [x] **Dashboard search through MCP** (`search_dashboards`), returning links back to Grafana
      for human review — the one capability named in the track requirement that was missing
- [x] Published tool inventory: the server advertises 72 tools, SLATE calls seven with a stated
      reason each, and the declines are listed with why rather than being silently absent

## Release tasks

- [ ] Record and publish the under-three-minute demo — script in `docs/DEMO-SCRIPT.md`
- [ ] Complete the Devpost submission — paste-ready copy in `docs/DEVPOST.md`
- [ ] Obtain review from a streaming or broadcast operations professional before making any
      stronger claim about operational fit (not obtained)

## Deliberately not done

- **Capacity starvation** as a failure class. It would need a real worker pool under
  contention; classifying it without one would be the same fiction this build just removed.
- **Grafana Cloud features** — the SLO app, IRM incidents, Sift, OnCall. The stack is
  self-hosted OSS, which the rules permit for unattended deployments, so those tools are not
  advertised by this server. Opening an incident would be the right next step on a Cloud stack.
- **`update_dashboard`.** Advertised and deliberately unused: the dashboard is provisioned from
  a file in this repository, and letting the agent rewrite it at runtime would make the
  operator's view something the model could change.
- **A score for Gemini's corroboration quality.** Assessed by inspection of deployed runs
  rather than reduced to a number this build could not defend.
