from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .gate import evaluate_jeopardy
from .grafana_mcp import GrafanaNotConfigured, write_annotation
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


def _configured(*names: str) -> bool:
    return all(bool(os.getenv(name)) for name in names)


@app.get("/", include_in_schema=False)
def landing_page() -> FileResponse:
    return FileResponse(os.path.join(WEB_ROOT, "index.html"))


@app.get("/health")
def health() -> dict[str, object]:
    google_vertex = _configured("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION") and os.getenv(
        "GOOGLE_GENAI_USE_VERTEXAI", ""
    ).lower() in {"1", "true", "yes"}
    grafana_mcp = _configured(
        "GRAFANA_MCP_COMMAND",
        "GRAFANA_PROMETHEUS_UID",
        "GRAFANA_LOKI_UID",
    )
    return {
        "status": "healthy",
        "service": "slate",
        "telemetry": "real_pipeline_measurements",
        "delivery_endpoint": "simulated",
        "integrations": {
            "google_vertex": google_vertex,
            "grafana_mcp": grafana_mcp,
            "otlp_export": bool(os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")),
            "agent_runtime_ready": google_vertex and grafana_mcp,
        },
    }


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
