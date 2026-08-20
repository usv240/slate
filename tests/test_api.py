from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from slate_app.main import app


def test_health_is_honest_about_simulated_endpoint():
    data = TestClient(app).get("/health").json()
    assert data["telemetry"] == "real_pipeline_measurements"
    assert data["delivery_endpoint"] == "simulated"
    assert data["integrations"]["grafana_mcp"] is False


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
