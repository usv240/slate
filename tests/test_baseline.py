"""The impact claim, made checkable.

SLATE does not claim to beat a failure alert to a failure, because a failure is instant
and nothing beats it. It claims a failure alert is answering a different
question, and that the difference costs delivery dates. These tests pin the two
disagreements that carry that argument, so the claim cannot quietly stop being
true.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from slate_app.baseline import compare, summarise
from slate_app.models import BurnObservation, DeliveryRecord, JobResult, RenditionSpec

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)


def specs(count: int) -> list[RenditionSpec]:
    return [
        RenditionSpec(name=f"r{index}", width=640, height=360, video_bitrate_kbps=800)
        for index in range(count)
    ]


def passed(name: str, seconds: float) -> JobResult:
    return JobResult(
        spec_name=name, status="passed", duration_seconds=seconds,
        exit_code=0, retries=0, output_bytes=1000,
    )


def failed(name: str) -> JobResult:
    return JobResult(
        spec_name=name, status="failed", duration_seconds=0.1, exit_code=8,
        retries=0, output_bytes=0, failure_class="codec_fault",
    )


def sustained_burn() -> list[BurnObservation]:
    return [
        BurnObservation(observed_at=NOW - timedelta(seconds=40), schedule_budget_seconds=200),
        BurnObservation(observed_at=NOW - timedelta(seconds=20), schedule_budget_seconds=100),
        BurnObservation(observed_at=NOW, schedule_budget_seconds=-50),
    ]


def invisible_miss() -> DeliveryRecord:
    """Everything encoded so far passed; the rest will not fit before the date."""

    return DeliveryRecord(
        delivery_id="del_invisible", title="Invisible miss",
        contractual_date=NOW + timedelta(hours=1), penalty_tier="premiere",
        specs=specs(8), fault_mode="none",
        jobs=[passed("r0", 1800), passed("r1", 1800)],
        pending_specs=6, p95_seconds_per_spec=1800,
        burn_observations=sustained_burn(),
    )


def cried_wolf() -> DeliveryRecord:
    """A rendition failed, and there are two days of slack to absorb it."""

    return DeliveryRecord(
        delivery_id="del_wolf", title="Cried wolf",
        contractual_date=NOW + timedelta(hours=48), penalty_tier="standard",
        specs=specs(2), fault_mode="wrong_codec",
        jobs=[failed("r0"), passed("r1", 1.0)],
        pending_specs=1, p95_seconds_per_spec=1.0,
    )


def verdict(record: DeliveryRecord, name: str) -> dict:
    return next(d for d in compare(record, NOW)["detectors"] if d["name"] == name)


def test_a_failure_alert_is_blind_to_a_miss_with_no_failure():
    """The case SLATE exists for, and the whole impact argument."""

    record = invisible_miss()
    assert not any(job.status == "failed" for job in record.jobs)
    assert verdict(record, "any_failure")["fired"] is False
    assert verdict(record, "deadline_passed")["fired"] is False
    slate = verdict(record, "slate_gate")
    assert slate["fired"] is True
    assert slate["lead_time_seconds"] == pytest.approx(3600, abs=1)
    assert compare(record, NOW)["disagreement"] == "invisible_miss"


def test_slate_stays_quiet_when_a_failure_will_not_cost_the_date():
    """Restraint is half the claim: an alert that always fires is not a signal."""

    record = cried_wolf()
    assert verdict(record, "any_failure")["fired"] is True
    assert verdict(record, "slate_gate")["fired"] is False
    assert compare(record, NOW)["disagreement"] == "cried_wolf"


def test_the_deadline_detector_is_never_early():
    """Included precisely because it is useless, and shows why lead time matters."""

    late = invisible_miss()
    late.contractual_date = NOW - timedelta(minutes=5)
    assert verdict(late, "deadline_passed")["fired"] is True
    assert verdict(late, "deadline_passed")["lead_time_seconds"] < 0


def test_the_summary_states_what_is_not_claimed():
    summary = summarise([compare(invisible_miss(), NOW), compare(cried_wolf(), NOW)])
    assert summary["invisible_miss"] == 1
    assert summary["cried_wolf"] == 1
    # The honest half: SLATE does not beat a failure alert to a hard failure.
    assert "does not show SLATE fires earlier" in summary["not_claimed"]


def test_comparison_reports_measured_inputs_not_projections():
    row = compare(invisible_miss(), NOW)
    assert row["measured_p95_seconds_per_spec"] == 1800
    assert row["pending_specs"] == 6
    assert row["work_remaining_seconds"] > 0
