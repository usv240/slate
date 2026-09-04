"""A key raises an allowance. It must never become a gate."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from slate_app import access
from slate_app.main import app


@pytest.fixture(autouse=True)
def clean_limiter(monkeypatch):
    access.limiter.reset()
    monkeypatch.setenv("SLATE_API_KEY_SECRET", "test-secret-not-a-real-one")
    yield
    access.limiter.reset()


def test_a_key_is_stateless_and_verifies_without_any_stored_record():
    issued = access.issue_key(label="judge")
    claims = access.verify_key(issued["api_key"])
    assert claims is not None
    assert claims["label"] == "judge"
    assert issued["stored_server_side"] is False


def test_a_tampered_key_is_rejected():
    issued = access.issue_key()["api_key"]
    payload, _, signature = issued[len(access.KEY_PREFIX) :].partition(".")
    forged = f"{access.KEY_PREFIX}{payload}.{'A' * len(signature)}"
    assert access.verify_key(forged) is None


def test_an_expired_key_is_rejected(monkeypatch):
    issued = access.issue_key()["api_key"]
    # Capture the real clock before patching: `access.time` is the shared module,
    # so a lambda calling time.time() would patch itself into infinite recursion.
    later = time.time() + access.KEY_TTL_SECONDS + 60
    monkeypatch.setattr(access.time, "time", lambda: later)
    assert access.verify_key(issued) is None


def test_a_bad_key_falls_back_to_anonymous_rather_than_locking_anyone_out():
    """The single most important property here.

    A key exists to raise a limit. If a malformed or expired key could reject a
    request, a judge who pasted the wrong string would be locked out of the
    product entirely, which is worse than having no keys at all.
    """

    decision = access.evaluate(authorization="Bearer slate_garbage.garbage", client_ip="1.2.3.4")
    assert decision.allowed is True
    assert decision.keyed is False
    assert decision.quota == access.ANONYMOUS_QUOTA


def test_a_key_raises_the_allowance():
    keyed = access.evaluate(
        authorization=f"Bearer {access.issue_key()['api_key']}", client_ip="1.2.3.4"
    )
    assert keyed.keyed is True
    assert keyed.quota == access.KEYED_QUOTA > access.ANONYMOUS_QUOTA


def test_the_anonymous_allowance_is_enforced_then_reports_how_long_to_wait():
    for _ in range(access.ANONYMOUS_QUOTA):
        assert access.evaluate(authorization=None, client_ip="9.9.9.9").allowed is True
    refused = access.evaluate(authorization=None, client_ip="9.9.9.9")
    assert refused.allowed is False
    assert refused.remaining == 0
    assert refused.reset_in > 0


def test_callers_are_counted_separately():
    for _ in range(access.ANONYMOUS_QUOTA):
        access.evaluate(authorization=None, client_ip="1.1.1.1")
    assert access.evaluate(authorization=None, client_ip="2.2.2.2").allowed is True


def test_reads_are_never_rate_limited():
    client = TestClient(app)
    for _ in range(access.ANONYMOUS_QUOTA + 4):
        assert client.get("/v1/deliveries").status_code == 200
        assert client.get("/health").status_code == 200


def test_the_key_endpoint_issues_and_explains_itself():
    body = TestClient(app).post("/v1/keys?label=judge").json()["data"]
    assert body["api_key"].startswith(access.KEY_PREFIX)
    assert body["quota_per_window"] == access.KEYED_QUOTA
    assert body["stored_server_side"] is False


def test_key_issuing_disabled_is_explained_not_hidden(monkeypatch):
    monkeypatch.delenv("SLATE_API_KEY_SECRET", raising=False)
    response = TestClient(app).post("/v1/keys")
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "key_issuing_disabled"
    # It must say the product still works without one.
    assert "anonymously" in detail["message"]


def test_an_abstention_costs_no_allowance(monkeypatch):
    """Calling the agent on a healthy delivery invokes no model, so it must be free."""

    from datetime import datetime, timedelta, timezone

    client = TestClient(app)
    payload = {
        "title": "Abstention is free",
        "contractual_date": (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat(),
        "specs": [{"name": "hd", "width": 640, "height": 360, "video_bitrate_kbps": 800}],
    }
    delivery_id = client.post("/v1/deliveries", json=payload).json()["data"]["delivery_id"]
    for _ in range(access.ANONYMOUS_QUOTA + 3):
        response = client.post(
            f"/v1/jeopardy/{delivery_id}/investigate", json={"operator_id": "judge"}
        )
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "abstained"


def test_the_demo_endpoint_is_honest_when_nothing_is_published(monkeypatch):
    monkeypatch.delenv("SLATE_DEMO_VIDEO_URL", raising=False)
    data = TestClient(app).get("/v1/demo").json()["data"]
    assert data["published"] is False
    assert data["embed_url"] is None
    assert "Not recorded yet" in data["note"]


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.youtube.com/watch?v=abc123XYZ", "https://www.youtube-nocookie.com/embed/abc123XYZ"),
        ("https://youtu.be/abc123XYZ", "https://www.youtube-nocookie.com/embed/abc123XYZ"),
        ("https://vimeo.com/987654321", "https://player.vimeo.com/video/987654321"),
    ],
)
def test_a_published_video_becomes_a_privacy_preserving_embed(monkeypatch, url, expected):
    monkeypatch.setenv("SLATE_DEMO_VIDEO_URL", url)
    data = TestClient(app).get("/v1/demo").json()["data"]
    assert data["published"] is True
    assert data["embed_url"] == expected
    assert data["watch_url"] == url


def test_presets_are_exactly_what_the_create_endpoint_accepts():
    """A preset must not be a privileged demo path.

    If loading a preset went through different code than a normal create, the
    presets would prove nothing about the product a judge can actually drive.
    """

    from slate_app.models import CreateDelivery
    from slate_app.presets import PRESETS

    client = TestClient(app)
    listed = client.get("/v1/presets").json()["data"]["presets"]
    assert len(listed) == len(PRESETS) >= 3

    for preset in listed:
        # The advertised body validates against the real request model...
        CreateDelivery.model_validate(preset["body"])
        # ...and the create endpoint accepts it unchanged.
        created = client.post("/v1/deliveries", json=preset["body"])
        assert created.status_code == 201, created.text
        record = created.json()["data"]
        assert record["title"] == preset["body"]["title"]
        assert len(record["specs"]) == preset["spec_count"]


def test_a_preset_downloads_as_an_editable_file():
    response = TestClient(app).get("/v1/presets/festival-encoder")
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    body = response.json()
    assert body["fault_mode"] == "wrong_codec"
    assert body["specs"], "a downloaded preset must carry its renditions"


def test_an_unknown_preset_says_which_ones_exist():
    response = TestClient(app).get("/v1/presets/does-not-exist")
    assert response.status_code == 404
    assert response.json()["detail"]["known"]


def test_a_custom_spec_ladder_is_accepted_and_drives_real_renditions():
    """The specs a judge types are the specs the pipeline runs."""

    from datetime import datetime, timedelta, timezone

    payload = {
        "title": "Judge's own ladder",
        "contractual_date": (datetime.now(timezone.utc) + timedelta(hours=8)).isoformat(),
        "specs": [
            {"name": "uhd", "width": 3840, "height": 2160, "video_codec": "libx265", "video_bitrate_kbps": 20000},
            {"name": "social", "width": 720, "height": 1280, "video_codec": "libx264", "video_bitrate_kbps": 2500},
        ],
    }
    record = TestClient(app).post("/v1/deliveries", json=payload).json()["data"]
    assert [s["name"] for s in record["specs"]] == ["uhd", "social"]
    assert record["specs"][0]["video_codec"] == "libx265"
    assert record["pending_specs"] == 2


def test_out_of_range_specs_are_refused_rather_than_silently_clamped():
    from datetime import datetime, timedelta, timezone

    payload = {
        "title": "Impossible ladder",
        "contractual_date": (datetime.now(timezone.utc) + timedelta(hours=8)).isoformat(),
        "specs": [{"name": "huge", "width": 99999, "height": 2160, "video_bitrate_kbps": 800}],
    }
    assert TestClient(app).post("/v1/deliveries", json=payload).status_code == 422


def test_promql_must_be_a_single_bounded_expression():
    client = TestClient(app)
    assert client.post("/v1/analyze/promql", json={"expr": "up\nup"}).status_code == 422
    assert client.post("/v1/analyze/promql", json={"expr": ""}).status_code == 422
    assert client.post("/v1/analyze/promql", json={"expr": "x" * 601}).status_code == 422


def test_promql_reaches_the_mcp_path_and_fails_closed_without_grafana():
    """Without Grafana configured it must report that, never invent a result."""

    response = TestClient(app).post(
        "/v1/analyze/promql", json={"expr": "sum(slate_queue_depth)"}
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "grafana_mcp_not_configured"
