"""The warning is only worth what can be done with the time it buys."""

from datetime import datetime, timedelta, timezone

from slate_app.intervention import MAX_EXTRA_WORKERS, outcomes
from slate_app.models import DeliveryRecord, RenditionSpec


def make_record(*, seconds_left: float, pending: int, p95: float, workers: int = 1):
    return DeliveryRecord(
        delivery_id="del_intervention",
        title="Fixture",
        contractual_date=datetime.now(timezone.utc) + timedelta(seconds=seconds_left),
        penalty_tier="premiere",
        specs=[RenditionSpec(name="proxy", width=320, height=180, video_bitrate_kbps=300)],
        fault_mode="none",
        pending_specs=pending,
        p95_seconds_per_spec=p95,
        active_workers=workers,
    )


def test_the_measured_miss_is_recoverable_with_one_more_worker():
    """These are the numbers the live eight-rendition proof actually produced."""

    result = outcomes(make_record(seconds_left=19.9, pending=5, p95=5.63))
    assert result["doing_nothing_lands"] is False
    assert result["recoverable"] is True
    assert result["cheapest_save"]["added_workers"] == 1
    assert result["cheapest_save"]["lands_before_contract"] is True
    # Doing nothing misses; one more worker lands with real slack to spare.
    assert result["options"][0]["slack_seconds"] < 0
    assert result["options"][1]["slack_seconds"] > 0


def test_a_delivery_that_is_already_fine_needs_no_intervention():
    result = outcomes(make_record(seconds_left=600, pending=2, p95=5.0))
    assert result["doing_nothing_lands"] is True
    assert result["cheapest_save"] is None


def test_some_misses_cannot_be_bought_back_and_it_says_so():
    """The projection must be able to return bad news, or it proves nothing."""

    result = outcomes(make_record(seconds_left=5, pending=40, p95=6.0))
    assert result["doing_nothing_lands"] is False
    assert result["recoverable"] is False
    assert result["cheapest_save"] is None
    assert all(not option["lands_before_contract"] for option in result["options"])


def test_added_workers_are_bounded_because_linear_speedup_is_not_defensible():
    result = outcomes(make_record(seconds_left=19.9, pending=5, p95=5.63))
    assert len(result["options"]) == MAX_EXTRA_WORKERS + 1
    assert max(option["workers"] for option in result["options"]) == 1 + MAX_EXTRA_WORKERS


def test_the_projection_states_what_it_is_not():
    result = outcomes(make_record(seconds_left=19.9, pending=5, p95=5.63))
    assert "not a second live run" in result["not_claimed"]
    assert "not a rate card" in result["measured_from"]
