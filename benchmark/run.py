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


FAULTS = {
    "poison_input": "poison_input",
    "wrong_codec": "codec_fault",
    "timeout": "timeout",
    "qc_rule_change": "qc_rule_change",
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
            observed = result.jobs[0].failure_class
            rows.append({
                "fault_mode": fault_mode,
                "expected_class": expected,
                "observed_class": observed,
                "correct": observed == expected,
                "real_pipeline_seconds": round(time.perf_counter() - started, 6),
                "job": result.jobs[0].model_dump(mode="json"),
            })
    durations = [row["real_pipeline_seconds"] for row in rows]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "media_fixture_type": "self_authored_lavfi_source_processed_by_real_ffmpeg",
        "delivery_receiver": "simulated",
        "fault_results": rows,
        "diagnosis_accuracy": sum(row["correct"] for row in rows) / len(rows),
        "pipeline_duration_seconds": {
            "median": round(statistics.median(durations), 6),
            "max": round(max(durations), 6),
        },
        "gate_evaluation": gate_evaluation(now),
        "limitations": [
            "Schedule histories are constructed evaluation fixtures and are not labelled as production telemetry.",
            "This benchmark evaluates deterministic fault labels, not Gemini's natural-language diagnosis quality.",
            "The delivery receiver is simulated; ingest, transcode and QC execution are real.",
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
        "diagnosis_accuracy": report["diagnosis_accuracy"],
        "false_jeopardy_rate": report["gate_evaluation"]["false_jeopardy_rate"],
        "lead_time_seconds": report["gate_evaluation"]["lead_time_seconds"],
    }, indent=2))


if __name__ == "__main__":
    main()
