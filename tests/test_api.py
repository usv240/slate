from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from slate_app.main import app
from slate_app.main import store as main_store


def test_health_is_honest_about_simulated_endpoint():
    data = TestClient(app).get("/health").json()
    assert data["telemetry"] == "real_pipeline_measurements"
    assert data["delivery_endpoint"] == "simulated"
    assert data["state_backend"] == "memory"
    assert data["integrations"]["grafana_mcp"] is False
    assert data["integrations"]["state_store"] is True


def test_grafana_evidence_is_unavailable_without_configuration():
    response = TestClient(app).get("/v1/integrations/grafana/evidence")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "grafana_mcp_not_configured"


def test_trace_lookup_rejects_non_trace_identifier():
    response = TestClient(app).get("/v1/integrations/grafana/traces/not-a-trace")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_trace_id"


def test_create_and_list_delivery():
    client = TestClient(app)
    payload = {
        "title": "Public-domain test package",
        "contractual_date": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
        "specs": [{"name":"hd","width":640,"height":360,"video_bitrate_kbps":800}],
        "fault_mode": "none",
    }
    created = client.post("/v1/deliveries", json=payload)
    assert created.status_code == 201
    delivery_id = created.json()["data"]["delivery_id"]
    listed = client.get("/v1/deliveries").json()["data"]
    assert delivery_id in {item["delivery_id"] for item in listed}


def test_remediation_requires_affirmative_human_approval():
    client = TestClient(app)
    payload = {
        "title": "Approval test",
        "contractual_date": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
        "specs": [{"name":"hd","width":640,"height":360,"video_bitrate_kbps":800}],
    }
    delivery_id = client.post("/v1/deliveries", json=payload).json()["data"]["delivery_id"]
    result = client.post(f"/v1/deliveries/{delivery_id}/remediation", json={"action":"increase_workers","operator_id":"judge","approved":False}).json()
    assert result["data"]["executed"] is False

def test_investigation_abstains_without_calling_a_model_when_gate_is_healthy():
    client = TestClient(app)
    payload = {
        "title": "Healthy abstention test",
        "contractual_date": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
        "specs": [{"name":"hd","width":640,"height":360,"video_bitrate_kbps":800}],
    }
    delivery_id = client.post("/v1/deliveries", json=payload).json()["data"]["delivery_id"]
    response = client.post(
        f"/v1/jeopardy/{delivery_id}/investigate",
        json={"operator_id": "judge"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "abstained"
    assert response.json()["data"]["model_called"] is False


def test_run_keeps_delivery_status_consistent_with_at_risk_gate(monkeypatch):
    from slate_app import main as main_module
    from slate_app.models import BurnObservation

    def fake_run(self, record):
        observed_now = datetime.now(timezone.utc)
        record.status = "degraded"
        record.package_complete = False
        record.pending_specs = 1
        record.p95_seconds_per_spec = 120
        record.retry_penalty_seconds = 120
        record.burn_observations = [
            BurnObservation(observed_at=observed_now - timedelta(seconds=20), schedule_budget_seconds=300),
            BurnObservation(observed_at=observed_now - timedelta(seconds=10), schedule_budget_seconds=200),
        ]
        return record

    class FakePipelineRunner:
        run = fake_run

    monkeypatch.setattr(main_module, "PipelineRunner", FakePipelineRunner)
    client = TestClient(app)
    payload = {
        "title": "State consistency test",
        "contractual_date": (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat(),
        "specs": [{"name":"hd","width":640,"height":360,"video_bitrate_kbps":800}],
    }
    delivery_id = client.post("/v1/deliveries", json=payload).json()["data"]["delivery_id"]
    response = client.post(f"/v1/deliveries/{delivery_id}/run")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["jeopardy"]["verdict"] == "at_risk"
    assert result["data"]["status"] == "at_risk"

def test_at_risk_investigation_invokes_the_adk_runtime(monkeypatch):
    import sys
    import types

    from slate_app import main as main_module
    from slate_app.models import BurnObservation, DeliveryRecord, RenditionSpec

    observed_now = datetime.now(timezone.utc)
    record = DeliveryRecord(
        delivery_id="del_agent_runtime_path",
        title="Agent runtime path",
        contractual_date=observed_now + timedelta(seconds=1),
        penalty_tier="priority",
        specs=[RenditionSpec(name="hd", width=640, height=360, video_bitrate_kbps=800)],
        fault_mode="none",
        status="at_risk",
        pending_specs=1,
        p95_seconds_per_spec=120,
        retry_penalty_seconds=120,
        burn_observations=[
            BurnObservation(observed_at=observed_now - timedelta(seconds=20), schedule_budget_seconds=300),
            BurnObservation(observed_at=observed_now - timedelta(seconds=10), schedule_budget_seconds=200),
            BurnObservation(observed_at=observed_now, schedule_budget_seconds=100),
        ],
    )
    main_module.store.put(record)
    calls = []

    async def fake_run_investigation(delivery, gate, *, operator_id):
        calls.append((delivery.delivery_id, gate.verdict, operator_id))
        return {"status": "completed", "outputs": {"watch": "evidence"}, "requires_human": True}

    fake_module = types.ModuleType("slate_app.adk_app")
    fake_module.AgentRuntimeNotConfigured = type("AgentRuntimeNotConfigured", (RuntimeError,), {})
    fake_module.run_investigation = fake_run_investigation
    monkeypatch.setitem(sys.modules, "slate_app.adk_app", fake_module)

    response = TestClient(app).post(
        "/v1/jeopardy/del_agent_runtime_path/investigate",
        json={"operator_id": "judge"},
    )
    assert response.status_code == 200, response.text
    assert calls == [("del_agent_runtime_path", "at_risk", "judge")]
    assert response.json()["data"]["status"] == "completed"


def test_report_export_is_a_downloadable_artifact():
    client = TestClient(app)
    payload = {
        "title": "Report export test",
        "contractual_date": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
        "specs": [{"name": "hd", "width": 640, "height": 360, "video_bitrate_kbps": 800}],
    }
    delivery_id = client.post("/v1/deliveries", json=payload).json()["data"]["delivery_id"]
    response = client.get(f"/v1/deliveries/{delivery_id}/report")
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    assert "Deterministic jeopardy gate" in response.text
    assert "simulated" in response.text


def test_approval_is_refused_for_an_action_the_agent_did_not_propose():
    client = TestClient(app)
    payload = {
        "title": "Bound approval test",
        "contractual_date": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
        "specs": [{"name": "hd", "width": 640, "height": 360, "video_bitrate_kbps": 800}],
    }
    delivery_id = client.post("/v1/deliveries", json=payload).json()["data"]["delivery_id"]
    record = main_store.get(delivery_id)
    record.last_investigation = {
        "remediation_plan": {
            "options": [
                {
                    "action": "requeue_safe",
                    "summary": "Re-run the failed rendition with the corrected encoder.",
                    "schedule_cost_seconds": 120,
                    "reversible": True,
                    "evidence": "Unknown encoder in stderr.",
                }
            ],
            "recommended_action": "requeue_safe",
            "why_a_human_decides": "The contractual date is the supervisor's to defend.",
        }
    }
    main_store.put(record)

    refused = client.post(
        f"/v1/deliveries/{delivery_id}/remediation",
        json={"action": "escalate_deadline", "operator_id": "judge", "approved": True},
    )
    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "action_not_proposed"

    allowed = client.post(
        f"/v1/deliveries/{delivery_id}/remediation",
        json={"action": "requeue_safe", "operator_id": "judge", "approved": True},
    )
    assert allowed.status_code == 200
    assert allowed.json()["data"]["human_approved"] is True


def test_delete_removes_the_delivery():
    client = TestClient(app)
    payload = {
        "title": "Delete test",
        "contractual_date": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
        "specs": [{"name": "hd", "width": 640, "height": 360, "video_bitrate_kbps": 800}],
    }
    delivery_id = client.post("/v1/deliveries", json=payload).json()["data"]["delivery_id"]
    assert client.delete(f"/v1/deliveries/{delivery_id}").json()["data"]["deleted"] is True
    assert client.get(f"/v1/jeopardy/{delivery_id}").status_code == 404
