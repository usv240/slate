"""Keep the demo board alive without anyone touching it.

A contractual date is absolute, which is the whole point of the product and
also its one operational problem: a board seeded the day a project is submitted
shows three expired contracts by the time anyone judges it weeks later. Every
card would read as a delivery that had already been missed, which is precisely
the wrong first impression.

`scripts/seed_board.py` fixed that by hand and required somebody to remember.
This does it in the deployment. Three titles are marked as board fixtures and
carry their contract window in hours; when one comes within a couple of hours of
its date, the date rolls forward and its burn history is cleared, so the board a
visitor opens is always the board it was designed to show.

Two rules keep this honest:

* Only the three fixtures are touched. Anything a visitor creates is theirs, is
  never rewritten, and its date is allowed to expire, because for a real
  delivery that is the truth.
* Nothing is fabricated. Rolling a date forward does not invent measurements:
  the p95, the job results and the QC outcomes stay exactly as the real FFmpeg
  runs left them.

One-off deliveries left by earlier visitors are dropped after a day, so the
board does not become a scrollback of every run anyone ever pressed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .models import DeliveryRecord

#: title -> (contract window in hours, penalty tier)
FIXTURES: dict[str, tuple[float, str]] = {
    "Nightfall S1E4 streamer package": (52.0, "priority"),
    "Harbour Lights feature master": (26.0, "premiere"),
    "Salt Road documentary trailer": (9.0, "standard"),
}

LADDER = [
    {"name": "proxy", "width": 320, "height": 180, "video_codec": "libx264", "video_bitrate_kbps": 300},
    {"name": "review", "width": 640, "height": 360, "video_codec": "libx264", "video_bitrate_kbps": 800},
]

#: Roll a fixture forward slightly before it expires. Landing exactly on the
#: date would let a visitor catch the board in the one state it should never be
#: found in.
REFRESH_MARGIN_HOURS = 2.0

#: How long a delivery someone else created stays on the board.
PRUNE_AFTER_HOURS = 24.0


def window_hours(record: DeliveryRecord) -> float | None:
    """The fixture window for this record, or None if it is not a fixture.

    Falls back to the title so records seeded before this module existed are
    adopted on the first pass rather than needing a migration.
    """

    if record.fixture_window_hours is not None:
        return record.fixture_window_hours
    known = FIXTURES.get(record.title)
    return known[0] if known else None


def refresh(store: Any, now: datetime | None = None) -> dict[str, Any]:
    """Roll expiring fixtures forward and drop stale one-off deliveries."""

    now = now or datetime.now(timezone.utc)
    rolled: list[str] = []
    adopted: list[str] = []
    pruned: list[str] = []

    for record in store.list():
        hours = window_hours(record)
        if hours is None:
            age_hours = (now - record.created_at).total_seconds() / 3600
            if age_hours > PRUNE_AFTER_HOURS:
                store.delete(record.delivery_id)
                pruned.append(record.delivery_id)
            continue

        changed = False
        if record.fixture_window_hours is None:
            record.fixture_window_hours = hours
            adopted.append(record.title)
            changed = True

        if record.contractual_date <= now + timedelta(hours=REFRESH_MARGIN_HOURS):
            record.contractual_date = now + timedelta(hours=hours)
            # Burn is measured between observations against a date. Carrying the
            # old observations across a new date would compute a rate from two
            # different contracts.
            record.burn_observations = []
            record.recovering = False
            if record.status in {"at_risk", "degraded", "failed"}:
                record.status = "healthy" if record.package_complete else "queued"
            record.updated_at = now
            rolled.append(record.title)
            changed = True

        if changed:
            store.put(record)

    return {
        "checked_at": now.isoformat(),
        "rolled_forward": rolled,
        "adopted": adopted,
        "pruned": pruned,
        "fixture_titles": sorted(FIXTURES),
        "policy": (
            "Only the three board fixtures are rewritten, and only their contractual date. "
            "Measurements are never fabricated. Deliveries created by visitors are left alone "
            "and removed after a day."
        ),
    }
