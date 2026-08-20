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


def test_real_poison_input_fails(tmp_path: Path):
    try:
        runner = PipelineRunner(tmp_path)
    except RuntimeError:
        pytest.skip("ffmpeg/ffprobe are not installed")
    result = runner.run(make_record("poison_input"))
    assert result.package_complete is False
    assert result.jobs[0].failure_class == "poison_input"
    assert result.pending_specs == 1
