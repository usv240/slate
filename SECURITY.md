# Security

Report vulnerabilities privately through GitHub's security-advisory flow for
`usv240/slate`. Do not open a public issue containing credentials or exploit
details.

## Trust boundaries

- Gemini explains evidence and proposes options. It cannot set the deterministic
  jeopardy verdict or execute remediation.
- Every remediation request must contain an affirmative human approval. The live
  contest deployment changes only synthetic delivery state and writes a Grafana
  annotation; it cannot reach a studio delivery receiver.
- Cloud Run uses `slate-runtime`, not a default project identity. It has Vertex,
  Firestore, and one-secret access only.
- The Grafana token and randomized OTLP path are held in Secret Manager. They are
  never returned by an API, stored in Git, or passed to Gemini.
- The MCP subprocess receives only `GRAFANA_URL` and its service-account token;
  Google credentials are deliberately excluded from its environment.
- Grafana anonymous access is Viewer-only and contains generated contest data.
  Administrative and write APIs require credentials.

The public build is a judging environment, not a real delivery control plane.
Before connecting it to studio systems, require identity-aware operator auth,
per-tenant authorization, rate limits, audit retention, and private ingress.
