from __future__ import annotations

import asyncio
import os
import time
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .gate import evaluate_jeopardy
from .grafana_mcp import (
    GrafanaMcp,
    GrafanaNotConfigured,
    query_loki,
    query_prometheus,
    query_tempo,
    write_annotation,
)
from .models import (
    BurnObservation,
    CreateDelivery,
    DeliveryRecord,
    InvestigationRequest,
    RemediationApproval,
)
from .pipeline import PipelineRunner
from .store import DeliveryStore
from .telemetry import SCHEDULE_BUDGET, event


app = FastAPI(title="SLATE API", version="0.2.0")
store = DeliveryStore()
WEB_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app", "web"))
_HEALTH_CACHE: dict[str, object] = {"checked_at": 0.0, "value": None}


def _configured(*names: str) -> bool:
    return all(bool(os.getenv(name)) for name in names)


@app.get("/", include_in_schema=False)
def landing_page() -> FileResponse:
    return FileResponse(os.path.join(WEB_ROOT, "index.html"))


def _probe_vertex() -> bool:
    from google import genai

    client = genai.Client(
        vertexai=True,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=os.environ["GOOGLE_CLOUD_LOCATION"],
    )
    response = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        contents="Reply with exactly OK.",
    )
    return bool(response.text)


async def _live_integrations() -> dict[str, bool]:
    now = time.monotonic()
    cached = _HEALTH_CACHE.get("value")
    if cached and now - float(_HEALTH_CACHE["checked_at"]) < 60:
        return dict(cached)
    google_configured = _configured("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION") and os.getenv(
        "GOOGLE_GENAI_USE_VERTEXAI", ""
    ).lower() in {"1", "true", "yes"}
    grafana_configured = _configured(
        "GRAFANA_MCP_COMMAND", "GRAFANA_URL", "GRAFANA_SERVICE_ACCOUNT_TOKEN",
        "GRAFANA_PROMETHEUS_UID", "GRAFANA_LOKI_UID",
        "GRAFANA_TEMPO_UID",
    )
    google_vertex = False
    grafana_mcp = False
    state_store = False
    try:
        state_store = await asyncio.to_thread(store.probe)
    except Exception:
        state_store = False
    if google_configured:
        try:
            google_vertex = await asyncio.to_thread(_probe_vertex)
        except Exception:
            google_vertex = False
    if grafana_configured:
        try:
            result = await query_prometheus('up{job="slate-cloud-run"}')
            grafana_mcp = not result["is_error"]
        except Exception:
            grafana_mcp = False
    value = {
        "google_vertex": google_vertex,
        "grafana_mcp": grafana_mcp,
        "state_store": state_store,
    }
    _HEALTH_CACHE.update(checked_at=now, value=value)
    return value


@app.get("/health")
async def health() -> dict[str, object]:
    live = await _live_integrations()
    return {
        "status": "healthy" if all(live.values()) else "degraded",
        "service": "slate",
        "telemetry": "real_pipeline_measurements",
        "delivery_endpoint": "simulated",
        "state_backend": store.backend,
        "integrations": {
            **live,
            "otlp_export": bool(os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")),
            "agent_runtime_ready": live["google_vertex"] and live["grafana_mcp"],
        },
    }


@app.get("/v1/integrations/grafana/evidence")
async def grafana_evidence() -> dict[str, object]:
    """Return live, read-only evidence acquired only through official Grafana MCP."""

    try:
        tools, prometheus, loki = await asyncio.gather(
            GrafanaMcp().advertised_tools(),
            query_prometheus('up{job="slate-cloud-run"}'),
            query_loki('{service_name="slate"} | json'),
        )
    except GrafanaNotConfigured as exc:
        raise HTTPException(503, detail={"code": "grafana_mcp_not_configured", "message": str(exc)}) from exc
    return {
        "data": {
            "transport": "official_mcp_grafana_stdio",
            "required_tools_advertised": {
                name: name in tools
                for name in ("query_prometheus", "query_loki_logs", "create_annotation")
            },
            "trace_tools_advertised": [
                name for name in tools if "tempo" in name.lower() or "trace" in name.lower()
            ],
            "prometheus": prometheus,
            "loki": loki,
        }
    }


@app.get("/v1/integrations/grafana/ai-observability")
async def grafana_ai_observability() -> dict[str, object]:
    """Ask Grafana what the agents themselves cost.

    SLATE's agents read the delivery pipeline through Grafana MCP. This closes
    the loop: the same MCP server is asked for the agents' own OpenTelemetry
    GenAI telemetry -- token usage by sub-agent, operation latency, and MCP tool
    activity -- so the system that watches the pipeline is itself watched.

    These series are emitted by slate_app/ai_telemetry.py using the gen_ai.*
    semantic conventions, which is what Grafana Cloud AI Observability consumes.
    """

    queries = {
        "tokens_by_agent": "sum by (agent, token_type) (slate_gen_ai_tokens_total)",
        # Mean, not p95: investigations are rare events, and a quantile over a
        # rate() window is undefined until several land inside it. An all-time
        # mean is a number that means what it says at this volume.
        "agent_mean_seconds": (
            "sum by (agent) (slate_gen_ai_operation_duration_seconds_sum) "
            "/ sum by (agent) (slate_gen_ai_operation_duration_seconds_count)"
        ),
        "mcp_tool_calls": "sum by (tool, outcome) (slate_mcp_tool_calls_total)",
        "mcp_tool_mean_seconds": (
            "sum by (tool) (slate_mcp_tool_duration_seconds_sum) "
            "/ sum by (tool) (slate_mcp_tool_duration_seconds_count)"
        ),
    }
    try:
        results = await asyncio.gather(*(query_prometheus(expr) for expr in queries.values()))
    except GrafanaNotConfigured as exc:
        raise HTTPException(
            503, detail={"code": "grafana_mcp_not_configured", "message": str(exc)}
        ) from exc
    return {
        "data": {
            "transport": "official_mcp_grafana_stdio",
            "convention": "opentelemetry gen_ai.* semantic conventions",
            "queries": queries,
            "results": dict(zip(queries.keys(), results)),
            "note": (
                "Emitted by the agent runtime itself. Empty series mean no investigation "
                "has run in this window, not that instrumentation is absent."
            ),
        }
    }


@app.get("/v1/integrations/grafana/traces/{trace_id}")
async def grafana_trace(trace_id: str) -> dict[str, object]:
    if len(trace_id) != 32 or any(character not in "0123456789abcdef" for character in trace_id.lower()):
        raise HTTPException(422, detail={"code": "invalid_trace_id", "message": "Expected a 32-character hex trace ID."})
    try:
        result = await query_tempo(trace_id.lower())
    except GrafanaNotConfigured as exc:
        raise HTTPException(503, detail={"code": "grafana_mcp_not_configured", "message": str(exc)}) from exc
    return {"data": {"transport": "official_mcp_grafana_stdio", "tempo": result}}


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/v1/deliveries", status_code=201)
def create_delivery(request: CreateDelivery) -> dict[str, object]:
    delivery_id = f"del_{uuid.uuid4().hex[:12]}"
    record = DeliveryRecord(delivery_id=delivery_id, pending_specs=len(request.specs), **request.model_dump())
    store.put(record)
    event(
        "delivery_created",
        delivery_id=delivery_id,
        title=record.title,
        contractual_date=record.contractual_date.isoformat(),
        specs=len(record.specs),
        fault_mode=record.fault_mode,
    )
    return {"data": record.model_dump(mode="json")}


@app.get("/v1/deliveries")
def list_deliveries() -> dict[str, object]:
    return {"data": [record.model_dump(mode="json") for record in store.list()]}


@app.post("/v1/deliveries/{delivery_id}/run")
def run_delivery(delivery_id: str) -> dict[str, object]:
    record = store.get(delivery_id)
    if not record:
        raise HTTPException(404, detail={"code": "delivery_not_found", "message": "Unknown delivery."})
    previous_status = record.status
    try:
        record = PipelineRunner().run(record)
    except RuntimeError as exc:
        raise HTTPException(503, detail={"code": "pipeline_unavailable", "message": str(exc)}) from exc
    pipeline_status = record.status
    now = datetime.now(timezone.utc)
    window = (record.contractual_date - now).total_seconds()
    workers = max(1, record.active_workers)
    work = ((record.pending_specs * record.p95_seconds_per_spec) + record.retry_penalty_seconds) / workers
    budget = window - work
    # Real pipeline outcomes supply observations. Rapid duplicate requests cannot
    # satisfy the gate because gate.py enforces a minimum evaluation-window length.
    record.burn_observations.append(BurnObservation(observed_at=now, schedule_budget_seconds=budget))
    SCHEDULE_BUDGET.labels(delivery_id=delivery_id).set(budget)
    gate = evaluate_jeopardy(record, now)
    if gate.verdict == "at_risk":
        record.status = "at_risk"
    elif previous_status == "at_risk" and record.package_complete:
        record.status = "recovered"
    else:
        record.status = pipeline_status
    store.put(record)
    return {
        "data": record.model_dump(mode="json"),
        "jeopardy": gate.model_dump(mode="json"),
    }


@app.get("/v1/jeopardy/{delivery_id}")
def jeopardy(delivery_id: str) -> dict[str, object]:
    record = store.get(delivery_id)
    if not record:
        raise HTTPException(404, detail={"code": "delivery_not_found", "message": "Unknown delivery."})
    return {"data": evaluate_jeopardy(record).model_dump(mode="json")}


@app.post("/v1/jeopardy/{delivery_id}/investigate")
async def investigate(delivery_id: str, request: InvestigationRequest) -> dict[str, object]:
    record = store.get(delivery_id)
    if not record:
        raise HTTPException(404, detail={"code": "delivery_not_found", "message": "Unknown delivery."})
    gate = evaluate_jeopardy(record)
    if gate.verdict != "at_risk":
        event(
            "agent_investigation_abstained",
            delivery_id=delivery_id,
            operator_id=request.operator_id,
            failed_thresholds=gate.gate["failed"],
        )
        return {
            "data": {
                "status": "abstained",
                "reason": "deterministic_gate_not_passed",
                "gate": gate.model_dump(mode="json"),
                "model_called": False,
                "requires_human": True,
            }
        }

    # Lazy import keeps ordinary pipeline requests independent of ADK startup,
    # while this request path demonstrably invokes the real Google ADK runner.
    from .adk_app import AgentRuntimeNotConfigured, run_investigation

    try:
        report = await run_investigation(record, gate, operator_id=request.operator_id)
    except (AgentRuntimeNotConfigured, GrafanaNotConfigured) as exc:
        raise HTTPException(
            503,
            detail={"code": "agent_runtime_not_configured", "message": str(exc)},
        ) from exc
    except Exception as exc:
        event(
            "agent_investigation_failed",
            delivery_id=delivery_id,
            operator_id=request.operator_id,
            error_type=type(exc).__name__,
        )
        raise HTTPException(
            502,
            detail={
                "code": "agent_investigation_failed",
                "message": "The Google ADK investigation did not complete; no verdict or remediation was changed.",
            },
        ) from exc
    return {"data": report, "gate": gate.model_dump(mode="json")}


@app.post("/v1/deliveries/{delivery_id}/remediation")
async def remediation(delivery_id: str, request: RemediationApproval) -> dict[str, object]:
    record = store.get(delivery_id)
    if not record:
        raise HTTPException(404, detail={"code": "delivery_not_found", "message": "Unknown delivery."})
    if not request.approved:
        event(
            "remediation_rejected",
            delivery_id=delivery_id,
            action=request.action,
            operator_id=request.operator_id,
        )
        return {"data": {"executed": False, "reason": "operator_rejected"}}

    if request.action == "increase_workers":
        record.active_workers = min(16, record.active_workers + 1)
    elif request.action == "requeue_safe":
        record.fault_mode = "none"
        record.pending_specs = len([job for job in record.jobs if job.status == "failed"])
        record.retry_penalty_seconds = record.pending_specs * record.p95_seconds_per_spec
        record.status = "queued"
        record.package_complete = False
        record.simulated_delivery_accepted = None
    # Contract priority and deadline escalation are recorded for a supervisor but
    # never mutate contractual truth automatically.
    gate = evaluate_jeopardy(record)
    if request.action == "increase_workers" and gate.verdict == "at_risk":
        record.status = "at_risk"
    store.put(record)
    annotation = None
    try:
        annotation = await write_annotation(
            f"Supervisor {request.operator_id} approved {request.action} for {delivery_id}",
            ["slate", "human-approved", request.action],
        )
    except GrafanaNotConfigured:
        annotation = {"written": False, "reason": "grafana_mcp_not_configured"}
    event(
        "remediation_approved",
        delivery_id=delivery_id,
        action=request.action,
        operator_id=request.operator_id,
        annotation_written=bool(annotation and annotation.get("written", True)),
    )
    return {
        "data": {
            "executed": request.action in {"increase_workers", "requeue_safe"},
            "action": request.action,
            "human_approved": True,
            "grafana_annotation": annotation,
            "jeopardy": gate.model_dump(mode="json"),
        }
    }
