from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .gate import evaluate_jeopardy
from .grafana_mcp import GrafanaNotConfigured, write_annotation
from .models import BurnObservation, CreateDelivery, DeliveryRecord, RemediationApproval
from .pipeline import PipelineRunner
from .store import DeliveryStore
from .telemetry import SCHEDULE_BUDGET, event


app = FastAPI(title="SLATE API", version="0.1.0")
store = DeliveryStore()
WEB_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app", "web"))


@app.get("/", include_in_schema=False)
def landing_page() -> FileResponse:
    return FileResponse(os.path.join(WEB_ROOT, "index.html"))


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "healthy",
        "service": "slate",
        "telemetry": "real_pipeline_measurements",
        "delivery_endpoint": "simulated",
        "integrations": {
            "google_vertex": bool(os.getenv("GOOGLE_CLOUD_PROJECT")),
            "grafana_mcp": bool(os.getenv("GRAFANA_MCP_COMMAND")),
            "otlp_export": bool(os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")),
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
    event("delivery_created", delivery_id=delivery_id, title=record.title, contractual_date=record.contractual_date.isoformat(), specs=len(record.specs), fault_mode=record.fault_mode)
    return {"data": record.model_dump(mode="json")}


@app.get("/v1/deliveries")
def list_deliveries() -> dict[str, object]:
    return {"data": [record.model_dump(mode="json") for record in store.list()]}


@app.post("/v1/deliveries/{delivery_id}/run")
def run_delivery(delivery_id: str) -> dict[str, object]:
    record = store.get(delivery_id)
    if not record:
        raise HTTPException(404, detail={"code": "delivery_not_found", "message": "Unknown delivery."})
    try:
        record = PipelineRunner().run(record)
    except RuntimeError as exc:
        raise HTTPException(503, detail={"code": "pipeline_unavailable", "message": str(exc)}) from exc
    now = datetime.now(timezone.utc)
    window = (record.contractual_date - now).total_seconds()
    work = record.pending_specs * record.p95_seconds_per_spec + record.retry_penalty_seconds
    budget = window - work
    # Real pipeline outcome supplies the current budget observation. Historical
    # observations arrive through subsequent runs/retries, never fabricated here.
    record.burn_observations.append(BurnObservation(observed_at=now, schedule_budget_seconds=budget))
    SCHEDULE_BUDGET.labels(delivery_id=delivery_id).set(budget)
    store.put(record)
    return {"data": record.model_dump(mode="json"), "jeopardy": evaluate_jeopardy(record).model_dump(mode="json")}


@app.get("/v1/jeopardy/{delivery_id}")
def jeopardy(delivery_id: str) -> dict[str, object]:
    record = store.get(delivery_id)
    if not record:
        raise HTTPException(404, detail={"code": "delivery_not_found", "message": "Unknown delivery."})
    return {"data": evaluate_jeopardy(record).model_dump(mode="json")}


@app.post("/v1/deliveries/{delivery_id}/remediation")
async def remediation(delivery_id: str, request: RemediationApproval) -> dict[str, object]:
    record = store.get(delivery_id)
    if not record:
        raise HTTPException(404, detail={"code": "delivery_not_found", "message": "Unknown delivery."})
    if not request.approved:
        event("remediation_rejected", delivery_id=delivery_id, action=request.action, operator_id=request.operator_id)
        return {"data": {"executed": False, "reason": "operator_rejected"}}
    if request.action == "increase_workers":
        record.active_workers = min(16, record.active_workers + 1)
    elif request.action == "requeue_safe":
        record.fault_mode = "none"
        record.pending_specs = len([job for job in record.jobs if job.status == "failed"])
    # Contract priority and deadline escalation are recorded for a supervisor but
    # never mutate contractual truth automatically.
    store.put(record)
    annotation = None
    try:
        annotation = await write_annotation(f"Supervisor {request.operator_id} approved {request.action} for {delivery_id}", ["slate", "human-approved", request.action])
    except GrafanaNotConfigured:
        annotation = {"written": False, "reason": "grafana_mcp_not_configured"}
    event("remediation_approved", delivery_id=delivery_id, action=request.action, operator_id=request.operator_id, annotation_written=bool(annotation and annotation.get("written", True)))
    return {"data": {"executed": request.action in {"increase_workers", "requeue_safe"}, "action": request.action, "human_approved": True, "grafana_annotation": annotation}}
