from datetime import datetime, timedelta, timezone

from slate_app.gate import evaluate_jeopardy
from slate_app.models import BurnObservation, DeliveryRecord, RenditionSpec


NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)


def record(*, deadline_seconds: float = 60, pending: int = 2, p95: float = 40, observations=None):
    return DeliveryRecord(
        delivery_id="del_test",
        title="Test delivery",
        contractual_date=NOW + timedelta(seconds=deadline_seconds),
        penalty_tier="priority",
        specs=[RenditionSpec(name="hd", width=640, height=360, video_bitrate_kbps=800)],
        fault_mode="none",
        pending_specs=pending,
        p95_seconds_per_spec=p95,
        burn_observations=observations or [],
    )


def sustained():
    return [
        BurnObservation(observed_at=NOW - timedelta(seconds=20), schedule_budget_seconds=30),
        BurnObservation(observed_at=NOW - timedelta(seconds=10), schedule_budget_seconds=20),
        BurnObservation(observed_at=NOW, schedule_budget_seconds=10),
    ]


def test_at_risk_requires_all_three_thresholds():
    result = evaluate_jeopardy(record(observations=sustained()), NOW)
    assert result.verdict == "at_risk"
    assert result.gate["failed"] == []
    assert result.requires_human is True


def test_one_burn_window_cannot_open_incident():
    observations = sustained()[:2]
    result = evaluate_jeopardy(record(observations=observations), NOW)
    assert result.verdict == "healthy"
    assert "positive_burn_sustained_two_windows" in result.gate["failed"]


def test_no_remaining_work_cannot_be_at_risk():
    result = evaluate_jeopardy(record(pending=0, observations=sustained()), NOW)
    assert result.verdict == "healthy"
    assert "work_remaining_positive" in result.gate["failed"]


def test_projected_completion_before_contract_is_healthy():
    result = evaluate_jeopardy(record(deadline_seconds=600, p95=10, observations=sustained()), NOW)
    assert result.verdict == "healthy"
    assert "projected_completion_after_contract" in result.gate["failed"]

def test_subsecond_observations_are_not_sustained_windows():
    observations = [
        BurnObservation(observed_at=NOW - timedelta(seconds=2), schedule_budget_seconds=30),
        BurnObservation(observed_at=NOW - timedelta(seconds=1), schedule_budget_seconds=20),
        BurnObservation(observed_at=NOW, schedule_budget_seconds=10),
    ]
    result = evaluate_jeopardy(record(observations=observations), NOW)
    assert result.verdict == "healthy"
    assert "positive_burn_sustained_two_windows" in result.gate["failed"]
    assert result.burn_rates == []
