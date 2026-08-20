# Limitations

- The final delivery receiver is simulated. Ingest, transcode, QC, packaging, failures, durations, retries, metrics, logs, and traces are real.
- The generated three-second engineering source proves the pipeline, not feature-length performance.
- The initial duration history is sparse; production p95 estimates require many more jobs grouped by codec/spec class.
- Cloud Run ephemeral state is suitable for a smoke build only. Production delivery state requires Firestore or another durable store.
- Grafana MCP and OTLP export fail closed until real credentials and endpoints exist.
- Predictive pre-miss alerting and schedule-budget thinking have prior art. This project does not claim conceptual novelty.
