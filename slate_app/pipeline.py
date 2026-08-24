from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from .models import DeliveryRecord, JobResult, RenditionSpec
from .telemetry import JOB_DURATION, JOB_FAILURES, JOB_RETRIES, QUEUE_DEPTH, event, stage_span


class PipelineRunner:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(os.getenv("SLATE_WORK_ROOT", "/tmp/slate"))
        self.root.mkdir(parents=True, exist_ok=True)
        self.ffmpeg = os.getenv("FFMPEG_BINARY") or shutil.which("ffmpeg")
        self.ffprobe = os.getenv("FFPROBE_BINARY") or shutil.which("ffprobe")
        if not self.ffmpeg:
            raise RuntimeError("ffmpeg is required; SLATE never substitutes simulated timings")

    def _run(self, args: list[str], timeout: float = 60) -> subprocess.CompletedProcess[str]:
        return subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=False)

    def _source(self, directory: Path, delivery_id: str) -> Path:
        source = directory / "source.mp4"
        with stage_span("ingest.generate_source", delivery_id=delivery_id):
            process = self._run([
                self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
                "-t", "3", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-shortest", str(source),
            ])
            if process.returncode:
                raise RuntimeError(f"source generation failed: {process.stderr[-500:]}")
            checksum = hashlib.sha256(source.read_bytes()).hexdigest()
            event("ingest_complete", delivery_id=delivery_id, bytes=source.stat().st_size, sha256=checksum)
        return source

    def _probe(self, output: Path) -> dict[str, object]:
        if self.ffprobe:
            process = self._run([self.ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name,width,height", "-of", "json", str(output)])
            if not process.returncode:
                return json.loads(process.stdout)

        # A self-contained FFmpeg binary may be present without FFprobe. This
        # still opens and decodes the actual output; it never trusts the request.
        process = self._run([self.ffmpeg, "-hide_banner", "-i", str(output), "-map", "0:v:0", "-frames:v", "1", "-f", "null", "-"])
        stream_line = next((line for line in process.stderr.splitlines() if "Video:" in line), "")
        codec = re.search(r"Video:\s*([a-zA-Z0-9_]+)", stream_line)
        dimensions = re.search(r"(?<![0-9])([1-9][0-9]{1,4})x([1-9][0-9]{1,4})(?![0-9])", stream_line)
        if not codec or not dimensions:
            return {}
        return {"streams": [{"codec_name": codec.group(1), "width": int(dimensions.group(1)), "height": int(dimensions.group(2))}]}

    def _transcode(self, record: DeliveryRecord, source: Path, spec: RenditionSpec, index: int) -> JobResult:
        started = time.perf_counter()
        output = source.parent / f"{spec.name}.mp4"
        input_path = source
        codec = spec.video_codec
        timeout = 60.0
        if record.fault_mode == "poison_input" and index == 0:
            input_path = source.parent / "poison.bin"
            input_path.write_bytes(b"not a media file\x00\x01")
        elif record.fault_mode == "wrong_codec" and index == 0:
            codec = "encoder_that_does_not_exist"
        elif record.fault_mode == "timeout" and index == 0:
            timeout = 0.001

        retries = 0
        failure_class = None
        exit_code = -1
        stderr = ""
        with stage_span("transcode.rendition", delivery_id=record.delivery_id, spec=spec.name, transform=f"{spec.width}x{spec.height}") as span:
            try:
                process = self._run([
                    self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(input_path),
                    "-vf", f"scale={spec.width}:{spec.height}", "-c:v", codec,
                    "-preset", "ultrafast", "-b:v", f"{spec.video_bitrate_kbps}k", "-an", str(output),
                ], timeout=timeout)
                exit_code = process.returncode
                stderr = process.stderr
            except subprocess.TimeoutExpired:
                failure_class = "timeout"
                stderr = "ffmpeg exceeded the real subprocess timeout"
            if exit_code != 0 and not failure_class:
                failure_class = "poison_input" if record.fault_mode == "poison_input" and index == 0 else "codec_fault" if record.fault_mode == "wrong_codec" and index == 0 else "transcode_failure"
            span.set_attribute("exit_code", exit_code)
            span.set_attribute("failure_class", failure_class or "none")

        qc_failures: list[str] = []
        if not failure_class:
            with stage_span("qc.rendition", delivery_id=record.delivery_id, spec=spec.name):
                streams = self._probe(output).get("streams", [])
                stream = streams[0] if streams else {}
                if stream.get("width") != spec.width or stream.get("height") != spec.height:
                    qc_failures.append("resolution_mismatch")
                expected_codec = "hevc" if spec.video_codec == "libx265" else "h264"
                if stream.get("codec_name") != expected_codec:
                    qc_failures.append("codec_mismatch")
                if record.fault_mode == "qc_rule_change" and index == 0:
                    qc_failures.append("new_textless_element_rule")
                if qc_failures:
                    failure_class = "qc_rule_change" if record.fault_mode == "qc_rule_change" and index == 0 else "qc_failure"

        duration = time.perf_counter() - started
        status = "failed" if failure_class or qc_failures else "passed"
        JOB_DURATION.labels(spec=spec.name, status=status).observe(duration)
        if failure_class:
            JOB_FAILURES.labels(failure_class=failure_class).inc()
        if retries:
            JOB_RETRIES.labels(spec=spec.name).inc(retries)
        event("rendition_complete", delivery_id=record.delivery_id, spec=spec.name, status=status, duration_seconds=duration, exit_code=exit_code, failure_class=failure_class, ffmpeg_stderr=stderr[-500:])
        return JobResult(spec_name=spec.name, status=status, duration_seconds=round(duration, 6), exit_code=exit_code, retries=retries, output_bytes=output.stat().st_size if output.exists() else 0, failure_class=failure_class, qc_failures=qc_failures)

    def run(self, record: DeliveryRecord) -> DeliveryRecord:
        directory = self.root / record.delivery_id
        directory.mkdir(parents=True, exist_ok=True)
        record.status = "running"
        record.pending_specs = len(record.specs)
        QUEUE_DEPTH.labels(delivery_id=record.delivery_id).set(record.pending_specs)
        with stage_span(
            "delivery.pipeline",
            delivery_id=record.delivery_id,
            title=record.title,
            fault_mode=record.fault_mode,
        ) as pipeline_span:
            context = pipeline_span.get_span_context()
            if context.is_valid:
                record.last_trace_id = format(context.trace_id, "032x")
            source = self._source(directory, record.delivery_id)
            jobs: list[JobResult] = []
            with ThreadPoolExecutor(max_workers=min(4, len(record.specs))) as executor:
                futures = {executor.submit(self._transcode, record, source, spec, index): spec for index, spec in enumerate(record.specs)}
                for future in as_completed(futures):
                    jobs.append(future.result())
                    record.pending_specs -= 1
                    QUEUE_DEPTH.labels(delivery_id=record.delivery_id).set(record.pending_specs)
            record.jobs = sorted(jobs, key=lambda item: item.spec_name)
            durations = sorted(job.duration_seconds for job in jobs)
            if durations:
                record.p95_seconds_per_spec = durations[min(len(durations) - 1, round(0.95 * len(durations)) - 1)]
            failed = [job for job in jobs if job.status == "failed"]
            # Failed renditions remain real outstanding work. Clearing the
            # queue here made the jeopardy gate mathematically unreachable.
            record.pending_specs = len(failed)
            QUEUE_DEPTH.labels(delivery_id=record.delivery_id).set(record.pending_specs)
            record.retry_penalty_seconds = sum(max(record.p95_seconds_per_spec, job.duration_seconds) for job in failed)
            with stage_span("package.manifest", delivery_id=record.delivery_id):
                manifest = {"delivery_id": record.delivery_id, "title": record.title, "generated_at": datetime.now(timezone.utc).isoformat(), "jobs": [job.model_dump() for job in record.jobs]}
                (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
                record.package_complete = not failed
            with stage_span("deliver.simulated_endpoint", delivery_id=record.delivery_id, simulated=True):
                record.simulated_delivery_accepted = record.package_complete
                event("simulated_delivery_result", delivery_id=record.delivery_id, accepted=record.simulated_delivery_accepted, reason="complete" if record.package_complete else "rendition_or_qc_failure")
        record.status = "healthy" if record.package_complete else "degraded"
        record.updated_at = datetime.now(timezone.utc)
        return record
