"""Reproducible SLATE fault and gate evaluation.

Media failures are produced by real FFmpeg executions. The schedule histories are
explicitly constructed evaluation fixtures, not production telemetry.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from slate_app.gate import evaluate_jeopardy
from slate_app.models import BurnObservation, DeliveryRecord, RenditionSpec
from slate_app.pipeline import PipelineRunner


#: scenario -> the class a correct classifier must derive from observed output.
#: The classifier never sees the scenario name; `slate_app.classify` is guarded by
#: a test asserting it cannot read the injected fault at all. `none` is a control:
#: a classifier that labels everything would fail it.
FAULTS = {
    "poison_input": "poison_input",
    "wrong_codec": "codec_fault",
    "timeout": "timeout",
    "qc_rule_change": "qc_failure",
    "none": None,
}


def record(delivery_id: str, fault_mode: str, deadline: datetime) -> DeliveryRecord:
    return DeliveryRecord(
        delivery_id=delivery_id,
        title=f"Evaluation: {fault_mode}",
        contractual_date=deadline,
        penalty_tier="priority",
        specs=[RenditionSpec(name="proxy", width=320, height=180, video_bitrate_kbps=300)],
        fault_mode=fault_mode,
        pending_specs=1,
    )


def measured_lead_time(p95_seconds: float, specs: int, contract_hours: float) -> dict[str, object]:
    """Lead time derived from the p95 this run actually measured.

    The schedule histories below are constructed fixtures for gate behaviour. This
    number is different: the per-spec cost comes from the FFmpeg jobs executed a
    moment ago, and it is projected onto a stated delivery size. The projection is
    stated so it cannot be read as an observed production result.
    """

    work_remaining = specs * p95_seconds
    window = contract_hours * 3600
    budget = window - work_remaining
    return {
        "basis": "p95 measured from this run's real FFmpeg jobs, projected onto a stated delivery size",
        "measured_p95_seconds_per_spec": round(p95_seconds, 6),
        "projected_specs": specs,
        "contract_window_hours": contract_hours,
        "work_remaining_seconds": round(work_remaining, 3),
        "schedule_budget_seconds": round(budget, 3),
        "jeopardy_visible_before_deadline_seconds": round(max(0.0, window - work_remaining), 3)
        if budget > 0
        else 0.0,
        "already_over_budget": budget <= 0,
    }


def gate_evaluation(now: datetime) -> dict[str, object]:
    base = record("gate_fixture", "none", now + timedelta(hours=6))
    base.p95_seconds_per_spec = 7 * 3600
    histories = {
        "transient_single_window": [
            BurnObservation(observed_at=now - timedelta(minutes=10), schedule_budget_seconds=1200),
            BurnObservation(observed_at=now - timedelta(minutes=5), schedule_budget_seconds=600),
        ],
        "sustained_two_windows": [
            BurnObservation(observed_at=now - timedelta(minutes=10), schedule_budget_seconds=1200),
            BurnObservation(observed_at=now - timedelta(minutes=5), schedule_budget_seconds=600),
            BurnObservation(observed_at=now, schedule_budget_seconds=0),
        ],
        "recovering_second_window": [
            BurnObservation(observed_at=now - timedelta(minutes=10), schedule_budget_seconds=1200),
            BurnObservation(observed_at=now - timedelta(minutes=5), schedule_budget_seconds=600),
            BurnObservation(observed_at=now, schedule_budget_seconds=900),
        ],
    }
    outcomes = {}
    for name, history in histories.items():
        candidate = base.model_copy(deep=True)
        candidate.burn_observations = history
        outcomes[name] = evaluate_jeopardy(candidate, now).model_dump(mode="json")
    negatives = ["transient_single_window", "recovering_second_window"]
    false_positives = sum(outcomes[name]["verdict"] == "at_risk" for name in negatives)
    detected = outcomes["sustained_two_windows"]["verdict"] == "at_risk"
    return {
        "fixture_type": "constructed_schedule_history",
        "lead_time_seconds": 6 * 3600 if detected else 0,
        "false_jeopardy_rate": false_positives / len(negatives),
        "outcomes": outcomes,
    }


def run(output: Path) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    rows: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="slate-eval-") as directory:
        runner = PipelineRunner(Path(directory))
        for index, (fault_mode, expected) in enumerate(FAULTS.items()):
            item = record(f"eval_{index}_{fault_mode}", fault_mode, now + timedelta(hours=1))
            started = time.perf_counter()
            result = runner.run(item)
            job = result.jobs[0]
            observed = job.failure_class
            rows.append({
                "scenario": fault_mode,
                "expected_class": expected,
                "observed_class": observed,
                "correct": observed == expected,
                "classified_from": {
                    "exit_code": job.exit_code,
                    "output_bytes": job.output_bytes,
                    "retries": job.retries,
                    "qc_failures": job.qc_failures,
                },
                "real_pipeline_seconds": round(time.perf_counter() - started, 6),
                "job": job.model_dump(mode="json"),
            })
    durations = [row["real_pipeline_seconds"] for row in rows]
    job_p95 = max((row["job"]["duration_seconds"] for row in rows), default=1.0)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "media_fixture_type": "self_authored_lavfi_source_processed_by_real_ffmpeg",
        "delivery_receiver": "simulated",
        "fault_results": rows,
        "classifier": {
            "source": "slate_app.classify, from FFmpeg stderr, exit status, output bytes and QC result",
            "sees_injected_scenario": False,
            "cases": len(rows),
            "correct": sum(row["correct"] for row in rows),
            "accuracy": sum(row["correct"] for row in rows) / len(rows),
            "misses": [row["scenario"] for row in rows if not row["correct"]],
        },
        "diagnosis_accuracy": sum(row["correct"] for row in rows) / len(rows),
        "measured_lead_time": measured_lead_time(job_p95, specs=120, contract_hours=6),
        "pipeline_duration_seconds": {
            "median": round(statistics.median(durations), 6),
            "max": round(max(durations), 6),
        },
        "gate_evaluation": gate_evaluation(now),
        "limitations": [
            "Five scenarios is engineering evidence, not a statistical accuracy claim.",
            "Schedule histories under gate_evaluation are constructed fixtures, not production telemetry.",
            "measured_lead_time projects a measured p95 onto a stated delivery size; the delivery size and contract window are assumptions, not observations.",
            "This benchmark scores the deterministic classifier. Gemini's corroboration quality is assessed separately and is not reduced to a number here.",
            "The delivery receiver is simulated; ingest, transcode, QC and packaging execution are real.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "benchmark" / "latest.json")
    args = parser.parse_args()
    report = run(args.output)
    print(json.dumps({
        "output": str(args.output),
        "classifier_accuracy": report["classifier"]["accuracy"],
        "classifier_misses": report["classifier"]["misses"],
        "false_jeopardy_rate": report["gate_evaluation"]["false_jeopardy_rate"],
        "lead_time_seconds": report["gate_evaluation"]["lead_time_seconds"],
    }, indent=2))


if __name__ == "__main__":
    main()
