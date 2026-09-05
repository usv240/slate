"""What a failure alert would have said, on the same real data.

SLATE's impact claim is not "we detect failures". Failures are already detected,
by every monitoring stack ever deployed. The claim is narrower and has to be
shown rather than asserted: a delivery can be going to miss its contractual date
while nothing has failed at all, and a detector that watches for failures cannot
see that no matter how good it is.

So the same measured run is put through three detectors and the disagreement is
reported:

* `any_failure`: fires as soon as a rendition fails. This is the ordinary alert.
* `deadline_passed`: fires when the contractual date has gone. Always correct,
  always useless.
* `slate_gate`: the deterministic three-threshold gate.

Two of the disagreements carry the argument:

* **Cried wolf.** A rendition failed, but the delivery still has hours of slack,
  so it will land on time. `any_failure` fires; SLATE stays quiet.
* **Invisible miss.** Every rendition passed and work remains that will not fit
  before the contractual date. `any_failure` is silent, and stays silent right up
  to the deadline. SLATE opens.

Nothing here is projected. Each verdict is computed from the delivery's own
measured p95, its real job results, and its real burn observations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .gate import evaluate_jeopardy
from .models import DeliveryRecord


@dataclass(frozen=True)
class DetectorVerdict:
    name: str
    fired: bool
    #: Seconds before the contractual date at which this detector would have
    #: fired, given what has actually been observed. Negative means the date had
    #: already passed.
    lead_time_seconds: float | None
    basis: str


def _seconds_to_contract(record: DeliveryRecord, now: datetime) -> float:
    return (record.contractual_date - now).total_seconds()


def any_failure_detector(record: DeliveryRecord, now: datetime) -> DetectorVerdict:
    """The ordinary alert: something broke, page someone."""

    failed = [job for job in record.jobs if job.status == "failed"]
    return DetectorVerdict(
        name="any_failure",
        fired=bool(failed),
        lead_time_seconds=_seconds_to_contract(record, now) if failed else None,
        basis=(
            f"{len(failed)} rendition(s) failed: "
            + ", ".join(sorted({job.failure_class or "unknown" for job in failed}))
            if failed
            else "no rendition has failed"
        ),
    )


def deadline_passed_detector(record: DeliveryRecord, now: datetime) -> DetectorVerdict:
    """The detector that is never wrong and never useful."""

    remaining = _seconds_to_contract(record, now)
    return DetectorVerdict(
        name="deadline_passed",
        fired=remaining <= 0,
        lead_time_seconds=remaining if remaining <= 0 else None,
        basis="the contractual date has passed" if remaining <= 0 else "the date has not passed yet",
    )


def slate_detector(record: DeliveryRecord, now: datetime) -> DetectorVerdict:
    gate = evaluate_jeopardy(record, now)
    fired = gate.verdict == "at_risk"
    return DetectorVerdict(
        name="slate_gate",
        fired=fired,
        lead_time_seconds=_seconds_to_contract(record, now) if fired else None,
        basis=(
            "projected completion is past the contract, burn is sustained, and work remains"
            if fired
            else "failed thresholds: " + ", ".join(gate.gate["failed"])
        ),
    )


def classify_disagreement(record: DeliveryRecord, now: datetime) -> tuple[str, str]:
    """Name what the two detectors disagree about, and why it matters."""

    naive = any_failure_detector(record, now)
    slate = slate_detector(record, now)
    will_miss = evaluate_jeopardy(record, now).verdict == "at_risk"

    if naive.fired and not slate.fired:
        return (
            "cried_wolf",
            "A rendition failed, but the measured work still fits before the contractual "
            "date. The ordinary alert fires; SLATE stays quiet because nothing is at risk.",
        )
    if slate.fired and not naive.fired:
        return (
            "invisible_miss",
            "Every rendition passed and the remaining work will not fit before the "
            "contractual date. A failure alert is silent here and stays silent until the "
            "date goes by. This is the case SLATE exists for.",
        )
    if slate.fired and naive.fired:
        return (
            "agreed_at_risk",
            "Both fire. SLATE adds why, how far past the date, and what it would cost to "
            "recover.",
        )
    return (
        "agreed_healthy",
        "Neither fires, and the delivery is on track." if not will_miss else "Neither fires.",
    )


def compare(record: DeliveryRecord, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    verdicts = [
        any_failure_detector(record, now),
        deadline_passed_detector(record, now),
        slate_detector(record, now),
    ]
    kind, explanation = classify_disagreement(record, now)
    gate = evaluate_jeopardy(record, now)
    return {
        "delivery_id": record.delivery_id,
        "title": record.title,
        "seconds_to_contract": round(_seconds_to_contract(record, now), 3),
        "work_remaining_seconds": gate.work_remaining_seconds,
        "measured_p95_seconds_per_spec": record.p95_seconds_per_spec,
        "pending_specs": record.pending_specs,
        "detectors": [
            {
                "name": verdict.name,
                "fired": verdict.fired,
                "lead_time_seconds": (
                    round(verdict.lead_time_seconds, 3)
                    if verdict.lead_time_seconds is not None
                    else None
                ),
                "basis": verdict.basis,
            }
            for verdict in verdicts
        ],
        "disagreement": kind,
        "why_it_matters": explanation,
    }


def summarise(comparisons: list[dict[str, Any]]) -> dict[str, Any]:
    kinds = [item["disagreement"] for item in comparisons]
    return {
        "deliveries_compared": len(comparisons),
        "invisible_miss": kinds.count("invisible_miss"),
        "cried_wolf": kinds.count("cried_wolf"),
        "agreed_at_risk": kinds.count("agreed_at_risk"),
        "agreed_healthy": kinds.count("agreed_healthy"),
        "claim": (
            "A failure alert cannot see a delivery that will miss its date without failing, "
            "and fires on failures that will not cost the date. Both are measured above from "
            "real pipeline runs, not projected."
        ),
        "not_claimed": (
            "This does not show SLATE fires earlier than a failure alert on a hard failure. "
            "It usually does not, because a failure is instant. It shows the failure alert is "
            "answering a different question."
        ),
    }
