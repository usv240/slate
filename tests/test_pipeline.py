from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from slate_app.models import DeliveryRecord, RenditionSpec
from slate_app.pipeline import PipelineRunner


def make_record(fault_mode="none"):
    return DeliveryRecord(
        delivery_id=f"del_{fault_mode}",
        title="Generated fixture",
        contractual_date=datetime.now(timezone.utc) + timedelta(hours=1),
        penalty_tier="standard",
        specs=[RenditionSpec(name="proxy", width=320, height=180, video_bitrate_kbps=300)],
        fault_mode=fault_mode,
        pending_specs=1,
    )


def test_real_ffmpeg_pipeline_passes(tmp_path: Path):
    try:
        runner = PipelineRunner(tmp_path)
    except RuntimeError:
        pytest.skip("ffmpeg/ffprobe are not installed")
    result = runner.run(make_record())
    assert result.package_complete is True
    assert result.jobs[0].status == "passed"
    assert result.jobs[0].duration_seconds > 0
    assert result.jobs[0].output_bytes > 0
    assert result.last_trace_id is not None
    assert len(result.last_trace_id) == 32


def test_real_poison_input_fails(tmp_path: Path):
    try:
        runner = PipelineRunner(tmp_path)
    except RuntimeError:
        pytest.skip("ffmpeg/ffprobe are not installed")
    result = runner.run(make_record("poison_input"))
    assert result.package_complete is False
    assert result.jobs[0].failure_class == "poison_input"
    assert result.pending_specs == 1
    assert result.last_trace_id is not None


@pytest.mark.parametrize(
    "scenario,expected",
    [
        ("none", None),
        ("poison_input", "poison_input"),
        ("wrong_codec", "codec_fault"),
        ("timeout", "timeout"),
        ("qc_rule_change", "qc_failure"),
    ],
)
def test_every_scenario_is_classified_from_real_ffmpeg_output(tmp_path: Path, scenario, expected):
    """The end-to-end guarantee behind the published classifier accuracy.

    Each scenario is turned into real configuration -- an unreadable file, a
    missing encoder, a real deadline, an extra conformance rule -- and the class
    must then be recovered from FFmpeg's own output. The classifier cannot read
    the scenario name, so a pass here is not a tautology.
    """

    try:
        runner = PipelineRunner(tmp_path)
    except RuntimeError:
        pytest.skip("ffmpeg is not installed")
    result = runner.run(make_record(scenario))
    assert result.jobs[0].failure_class == expected


def test_no_telemetry_the_agent_reads_carries_the_injected_scenario(tmp_path: Path):
    """A judge reading the telemetry must not find the answer written on it.

    The delivery record keeps `fault_mode`, because that is the operator's own
    request configuration and it is what `plan` turns into real inputs. What
    must not carry it is anything the agents can read: the job result behind the
    Prometheus labels and the Loki events, and the pipeline span's attributes.
    The agents receive Grafana evidence and the gate result, never the record.
    """

    try:
        runner = PipelineRunner(tmp_path)
    except RuntimeError:
        pytest.skip("ffmpeg is not installed")
    record = make_record("wrong_codec")
    record.title = "Scenario name must not leak into telemetry"
    result = runner.run(record)

    job = result.jobs[0]
    assert job.failure_class == "codec_fault"
    # The class was recovered from FFmpeg's own words, so the raw evidence is
    # allowed to travel; the scenario label is not.
    assert "wrong_codec" not in job.model_dump_json()
    assert "Scenario name must not leak" not in job.model_dump_json()

    # And the gate result the agents are given carries neither.
    from slate_app.gate import evaluate_jeopardy

    gate = evaluate_jeopardy(result).model_dump_json()
    assert "wrong_codec" not in gate
    assert "Scenario name must not leak" not in gate


def test_deterministic_failures_are_not_retried(tmp_path: Path):
    try:
        runner = PipelineRunner(tmp_path)
    except RuntimeError:
        pytest.skip("ffmpeg is not installed")
    result = runner.run(make_record("wrong_codec"))
    assert result.jobs[0].retries == 0


def test_batching_leaves_real_pending_work_with_nothing_failed(tmp_path: Path):
    """The invisible-miss case has to be reachable from real runs, not fabricated.

    A facility works a delivery queue in waves. Encoding two of eight renditions
    leaves six genuinely outstanding, every one of them passing, which is exactly
    the state a failure-watching alert cannot see.
    """

    try:
        runner = PipelineRunner(tmp_path)
    except RuntimeError:
        pytest.skip("ffmpeg is not installed")
    record = make_record()
    record.specs = [
        RenditionSpec(name=f"r{i}", width=320, height=180, video_bitrate_kbps=300) for i in range(6)
    ]
    record.pending_specs = 6

    result = runner.run(record, limit=2)
    assert [job.status for job in result.jobs] == ["passed", "passed"]
    assert result.pending_specs == 4, "un-encoded renditions are still outstanding work"
    assert result.package_complete is False
    assert result.p95_seconds_per_spec > 0

    result = runner.run(result, limit=2)
    assert len(result.jobs) == 4
    assert result.pending_specs == 2
    assert all(job.status == "passed" for job in result.jobs)


def test_a_completed_queue_reports_no_outstanding_work(tmp_path: Path):
    try:
        runner = PipelineRunner(tmp_path)
    except RuntimeError:
        pytest.skip("ffmpeg is not installed")
    result = runner.run(make_record())
    assert result.pending_specs == 0
    assert result.package_complete is True
