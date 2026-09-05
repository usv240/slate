"""The board has to survive the gap between submitting and being judged."""

from datetime import datetime, timedelta, timezone

from slate_app.fixtures import FIXTURES, PRUNE_AFTER_HOURS, refresh
from slate_app.models import DeliveryRecord, JobResult, RenditionSpec
from slate_app.store import DeliveryStore


def make(title, *, hours_from_now, created_hours_ago=0.0, status="healthy", fixture=None):
    now = datetime.now(timezone.utc)
    return DeliveryRecord(
        delivery_id=f"del_{abs(hash((title, hours_from_now, created_hours_ago))) % 10**10}",
        title=title,
        contractual_date=now + timedelta(hours=hours_from_now),
        penalty_tier="standard",
        specs=[RenditionSpec(name="proxy", width=320, height=180, video_bitrate_kbps=300)],
        fault_mode="none",
        status=status,
        created_at=now - timedelta(hours=created_hours_ago),
        package_complete=True,
        p95_seconds_per_spec=0.52,
        jobs=[JobResult(spec_name="proxy", status="passed", duration_seconds=0.52,
                        output_bytes=1024, retries=0, exit_code=0)],
        fixture_window_hours=fixture,
    )


def test_an_expired_fixture_is_rolled_forward_not_left_dead():
    store = DeliveryStore()
    store.put(make("Salt Road documentary trailer", hours_from_now=-40, fixture=9.0))
    result = refresh(store)
    assert result["rolled_forward"] == ["Salt Road documentary trailer"]
    record = store.list()[0]
    assert record.contractual_date > datetime.now(timezone.utc)
    assert record.status == "healthy"


def test_rolling_a_date_forward_never_invents_a_measurement():
    """The date is the only thing allowed to move."""

    store = DeliveryStore()
    store.put(make("Harbour Lights feature master", hours_from_now=-3, fixture=26.0))
    before = store.list()[0]
    p95, jobs = before.p95_seconds_per_spec, len(before.jobs)
    refresh(store)
    after = store.list()[0]
    assert after.p95_seconds_per_spec == p95
    assert len(after.jobs) == jobs
    assert after.jobs[0].duration_seconds == 0.52


def test_a_fixture_seeded_before_this_existed_is_adopted_by_title():
    store = DeliveryStore()
    store.put(make("Nightfall S1E4 streamer package", hours_from_now=-1, fixture=None))
    result = refresh(store)
    assert "Nightfall S1E4 streamer package" in result["adopted"]
    assert store.list()[0].fixture_window_hours == FIXTURES["Nightfall S1E4 streamer package"][0]


def test_a_healthy_fixture_is_left_completely_alone():
    store = DeliveryStore()
    store.put(make("Salt Road documentary trailer", hours_from_now=8, fixture=9.0))
    original = store.list()[0].contractual_date
    result = refresh(store)
    assert result["rolled_forward"] == []
    assert store.list()[0].contractual_date == original


def test_a_visitors_delivery_is_never_rewritten_even_when_it_expires():
    """For a real delivery, an expired date is the truth and must show."""

    store = DeliveryStore()
    store.put(make("A judge's own delivery", hours_from_now=-2, status="at_risk"))
    result = refresh(store)
    assert result["rolled_forward"] == []
    record = store.list()[0]
    assert record.contractual_date < datetime.now(timezone.utc)
    assert record.status == "at_risk"


def test_stale_one_off_deliveries_are_dropped_so_the_board_stays_readable():
    store = DeliveryStore()
    store.put(make("Old run someone left", hours_from_now=-50, created_hours_ago=PRUNE_AFTER_HOURS + 5))
    store.put(make("Run from ten minutes ago", hours_from_now=4, created_hours_ago=0.2))
    result = refresh(store)
    assert len(result["pruned"]) == 1
    assert [r.title for r in store.list()] == ["Run from ten minutes ago"]
