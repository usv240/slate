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


QC_RULES = ("resolution", "codec", "textless_elements")


class CreateDelivery(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    contractual_date: datetime
    penalty_tier: Literal["standard", "priority", "premiere"] = "standard"
    specs: list[RenditionSpec] = Field(min_length=1, max_length=8)
    fault_mode: FaultMode = "none"
    qc_rules: list[Literal[QC_RULES]] = ["resolution", "codec"]

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
    qc_rules: list[str] = ["resolution", "codec"]
    package_complete: bool = False
    simulated_delivery_accepted: bool | None = None
    last_trace_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    alert_rule: dict[str, object] | None = None
    recovering: bool = False
    last_investigation: dict[str, object] | None = None
    decisions: list[dict[str, object]] = []


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


REMEDIATION_ACTIONS = ("requeue_safe", "increase_workers", "prioritize_contract", "escalate_deadline")


class RemediationOption(BaseModel):
    """One bounded option the Remediate agent may put in front of an operator.

    `action` is constrained to the four actions the API can actually perform, so
    the agent cannot propose something the product has no way to carry out, and
    the board can render each option as a real approval button.
    """

    action: Literal[REMEDIATION_ACTIONS]
    summary: str = Field(min_length=4, max_length=240)
    schedule_cost_seconds: float = Field(ge=0, le=2_592_000)
    reversible: bool
    evidence: str = Field(min_length=4, max_length=600)


class RemediationPlan(BaseModel):
    """Structured output contract for the Remediate agent."""

    options: list[RemediationOption] = Field(min_length=1, max_length=4)
    recommended_action: Literal[REMEDIATION_ACTIONS]
    why_a_human_decides: str = Field(min_length=4, max_length=400)


class RemediationApproval(BaseModel):
    action: Literal[REMEDIATION_ACTIONS]
    operator_id: str = Field(min_length=2, max_length=120)
    approved: bool


class InvestigationRequest(BaseModel):
    operator_id: str = Field(min_length=2, max_length=120)
