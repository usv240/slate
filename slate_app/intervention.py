"""What the warning actually buys the supervisor.

A detector that fires earlier is only worth something if the extra time can be
spent. This module answers the question a delivery supervisor actually asks when
an alert arrives: *if I act now, does the delivery land?*

Every number here comes from the p95 the renditions in this delivery just
measured. Nothing is a rate card, an industry average, or a guess. The one
modelling assumption is that granting a worker lets the remaining renditions
encode that much more concurrently, and that assumption is not free: the
pipeline pool is sized from `active_workers`, and
`tests/test_pipeline.py::test_the_pipeline_never_runs_wider_than_the_gate_assumes`
fails the build if the executor ever runs wider than the gate assumed. Before
that check existed the pool was pinned at four while the gate projected serial
work, so approving `increase_workers` moved the arithmetic without moving the
clock.

The honest limit is stated with the result rather than left for a reader to
find: this is arithmetic over a measured p95, not a second live run. Encoding is
not perfectly parallel, and a real facility's farm is shared.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .models import DeliveryRecord

#: How many extra workers a supervisor is offered. Beyond a handful the
#: assumption of near-linear speedup stops being defensible, and offering
#: sixteen would be selling a number we cannot stand behind.
MAX_EXTRA_WORKERS = 3


def _work_remaining(record: DeliveryRecord, workers: int) -> float:
    raw = (record.pending_specs * record.p95_seconds_per_spec) + record.retry_penalty_seconds
    return raw / max(1, workers)


def outcomes(record: DeliveryRecord, now: datetime | None = None) -> dict[str, object]:
    """Project the delivery under the current plan and under added workers."""

    now = now or datetime.now(timezone.utc)
    window = (record.contractual_date - now).total_seconds()
    current = max(1, record.active_workers)

    options = []
    for extra in range(0, MAX_EXTRA_WORKERS + 1):
        workers = current + extra
        work = _work_remaining(record, workers)
        options.append(
            {
                "workers": workers,
                "added_workers": extra,
                "action": "no_action" if extra == 0 else "increase_workers",
                "projected_work_seconds": round(work, 2),
                "slack_seconds": round(window - work, 2),
                "lands_before_contract": work <= window,
            }
        )

    doing_nothing = options[0]
    # There is no save to offer when the delivery already lands. Reporting one
    # would turn a healthy title into a prompt to spend capacity it does not need.
    saves = (
        []
        if doing_nothing["lands_before_contract"]
        else [option for option in options[1:] if option["lands_before_contract"]]
    )
    return {
        "delivery_id": record.delivery_id,
        "evaluated_at": now.isoformat(),
        "window_seconds": round(window, 2),
        "p95_seconds_per_spec": round(record.p95_seconds_per_spec, 3),
        "pending_specs": record.pending_specs,
        "current_workers": current,
        "options": options,
        "doing_nothing_lands": doing_nothing["lands_before_contract"],
        "cheapest_save": saves[0] if saves else None,
        "recoverable": bool(saves),
        "measured_from": (
            "the p95 of the renditions this delivery has already encoded, not a rate card"
        ),
        "not_claimed": (
            "This is arithmetic over a measured p95, not a second live run. Encoding is not "
            "perfectly parallel and a real farm is shared, so treat the added-worker rows as "
            "the best case that the pipeline is at least configured to attempt."
        ),
    }
