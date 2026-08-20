from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, model_validator


FaultMode = Literal["none", "poison_input", "wrong_codec", "timeout", "qc_rule_change"]
DeliveryStatus = Literal["queued", "running", "healthy", "degraded", "at_risk", "recovered", "failed"]


class RenditionSpec(BaseModel):
    name: str = Field(pattern=r"^[a-z0-9_-]{2,40}$")
    width: int = Field(ge=160, le=3840)
    height: int = Field(ge=90, le=2160)
    video_codec: Literal["libx264", "libx265"] = "libx264"
    video_bitrate_kbps: int = Field(ge=100, le=50_000)


class CreateDelivery(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    contractual_date: datetime
    penalty_tier: Literal["standard", "priority", "premiere"] = "standard"
    specs: list[RenditionSpec] = Field(min_length=1, max_length=8)
    fault_mode: FaultMode = "none"

    @model_validator(mode="after")
    def deadline_is_aware(self) -> "CreateDelivery":
        if self.contractual_date.tzinfo is None:
            raise ValueError("contractual_date must include a timezone")
        return self


class JobResult(BaseModel):
    spec_name: str
    status: Literal["passed", "failed"]
    duration_seconds: float = Field(ge=0)
    exit_code: int
    retries: int = Field(ge=0)
    output_bytes: int = Field(ge=0)
    failure_class: str | None = None
    qc_failures: list[str] = []


class BurnObservation(BaseModel):
    observed_at: datetime
    schedule_budget_seconds: float


class DeliveryRecord(BaseModel):
    delivery_id: str
    title: str
    contractual_date: datetime
    penalty_tier: Literal["standard", "priority", "premiere"]
    specs: list[RenditionSpec]
    fault_mode: FaultMode
    status: DeliveryStatus = "queued"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    jobs: list[JobResult] = []
    pending_specs: int = 0
    p95_seconds_per_spec: float = 8.0
    active_workers: int = 1
    retry_penalty_seconds: float = 0
    burn_observations: list[BurnObservation] = []
    package_complete: bool = False
    simulated_delivery_accepted: bool | None = None


class ThresholdResult(BaseModel):
    name: str
    passed: bool
    observed: float | int | bool | str
    required: str


class JeopardyResult(BaseModel):
    verdict: Literal["healthy", "at_risk"]
    severity: Literal["none", "warning", "critical"]
    calculated_at: datetime
    delivery_window_seconds: float
    work_remaining_seconds: float
    schedule_budget_seconds: float
    burn_rates: list[float]
    projected_completion: datetime
    hours_over: float
    thresholds: list[ThresholdResult]
    gate: dict[str, list[str]]
    requires_human: bool = True


class RemediationApproval(BaseModel):
    action: Literal["requeue_safe", "increase_workers", "prioritize_contract", "escalate_deadline"]
    operator_id: str = Field(min_length=2, max_length=120)
    approved: bool


class InvestigationRequest(BaseModel):
    operator_id: str = Field(min_length=2, max_length=120)
