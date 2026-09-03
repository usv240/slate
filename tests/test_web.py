from fastapi.testclient import TestClient

from slate_app.main import app


def test_landing_page_exposes_truth_boundary_and_modes():
    response = TestClient(app).get("/")
    assert response.status_code == 200
    assert "FFmpeg execution and telemetry are real" in response.text
    assert "External delivery receiver is simulated" in response.text
    assert "Plain" in response.text
    assert "Technical" in response.text
    assert "Run 20s judge proof" in response.text
    assert "/v1/integrations/grafana/evidence" in response.text
    assert "Grafana control tower" in response.text


def test_landing_page_links_the_dashboard_that_actually_exists():
    """The provisioned dashboard UID is slate-delivery-slo.

    The page previously linked /d/slate-delivery/..., which renders Grafana's
    "Dashboard not found" page. It was the only partner-facing link on the page.
    """

    response = TestClient(app).get("/")
    assert "/d/slate-delivery-slo/" in response.text
    assert "/d/slate-delivery/slate-delivery-control-tower" not in response.text


def test_landing_page_offers_light_default_with_opt_in_dark():
    response = TestClient(app).get("/")
    assert 'data-theme="dark"' in response.text
    assert "prefers-reduced-motion" in response.text


def test_metrics_expose_pipeline_series():
    response = TestClient(app).get("/metrics")
    assert response.status_code == 200
    assert "slate_job_duration_seconds" in response.text
    assert "slate_schedule_budget_seconds" in response.text
