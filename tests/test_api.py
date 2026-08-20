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
