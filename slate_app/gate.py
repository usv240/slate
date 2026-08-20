from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from .models import BurnObservation, DeliveryRecord, JeopardyResult, ThresholdResult


_PENALTY_WEIGHT = {"standard": 1, "priority": 2, "premiere": 3}
_DEFAULT_MIN_BURN_WINDOW_SECONDS = 5.0


def _minimum_window_seconds() -> float:
    configured = float(os.getenv("SLATE_MIN_BURN_WINDOW_SECONDS", str(_DEFAULT_MIN_BURN_WINDOW_SECONDS)))
    if configured <= 0:
        raise ValueError("SLATE_MIN_BURN_WINDOW_SECONDS must be positive")
    return configured


def _burn_rates(observations: list[BurnObservation], minimum_window_seconds: float) -> list[float]:
    ordered = sorted(observations, key=lambda item: item.observed_at)
    rates: list[float] = []
    for previous, current in zip(ordered, ordered[1:]):
        elapsed = (current.observed_at - previous.observed_at).total_seconds()
        # A burst of duplicate requests is not sustained evidence. Each rate must
        # represent a real evaluation window before it may contribute to the gate.
        if elapsed < minimum_window_seconds:
            continue
        consumed = previous.schedule_budget_seconds - current.schedule_budget_seconds
        rates.append(max(0.0, consumed / elapsed))
    return rates


def evaluate_jeopardy(delivery: DeliveryRecord, now: datetime | None = None) -> JeopardyResult:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must include a timezone")
    delivery_window = (delivery.contractual_date - now).total_seconds()
    workers = max(1, delivery.active_workers)
    work_remaining = ((delivery.pending_specs * delivery.p95_seconds_per_spec) + delivery.retry_penalty_seconds) / workers
    schedule_budget = delivery_window - work_remaining
    projected_completion = now + timedelta(seconds=max(0, work_remaining))
    minimum_window_seconds = _minimum_window_seconds()
    rates = _burn_rates(delivery.burn_observations, minimum_window_seconds)
    sustained = len(rates) >= 2 and all(rate > 0 for rate in rates[-2:])
    projected_late = projected_completion > delivery.contractual_date
    has_work = work_remaining > 0

    thresholds = [
        ThresholdResult(name="projected_completion_after_contract", passed=projected_late, observed=projected_completion.isoformat(), required=f"> {delivery.contractual_date.isoformat()}"),
        ThresholdResult(name="positive_burn_sustained_two_windows", passed=sustained, observed=len([rate for rate in rates[-2:] if rate > 0]), required=f"2 consecutive positive windows, each >= {minimum_window_seconds:g}s"),
        ThresholdResult(name="work_remaining_positive", passed=has_work, observed=round(work_remaining, 3), required="> 0 seconds"),
    ]
    at_risk = all(item.passed for item in thresholds)
    hours_over = max(0.0, (projected_completion - delivery.contractual_date).total_seconds() / 3600)
    weighted = hours_over * _PENALTY_WEIGHT[delivery.penalty_tier] * max(1, delivery.pending_specs)
    severity = "critical" if at_risk and weighted >= 1 else "warning" if at_risk else "none"
    passed = [item.name for item in thresholds if item.passed]
    failed = [item.name for item in thresholds if not item.passed]
    return JeopardyResult(
        verdict="at_risk" if at_risk else "healthy",
        severity=severity,
        calculated_at=now,
        delivery_window_seconds=round(delivery_window, 3),
        work_remaining_seconds=round(work_remaining, 3),
        schedule_budget_seconds=round(schedule_budget, 3),
        burn_rates=[round(rate, 6) for rate in rates],
        projected_completion=projected_completion,
        hours_over=round(hours_over, 6),
        thresholds=thresholds,
        gate={"passed": passed, "failed": failed},
    )
