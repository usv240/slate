from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .classify import classify, is_retryable
from .models import DeliveryRecord, JobResult, RenditionSpec
from .telemetry import JOB_DURATION, JOB_FAILURES, JOB_RETRIES, QUEUE_DEPTH, event, stage_span


DEFAULT_QC_RULES = ("resolution", "codec")


@dataclass
class JobPlan:
    """What this job will actually execute.

    The requested scenario is consumed here, once, and turned into real
    configuration: a real input path, a real encoder name, a real timeout, a real
    QC rule set. After this object is built nothing downstream may look at the
    scenario again, so the failure class can only come from observed output.
    """

    spec: RenditionSpec
    input_path: Path
    output_path: Path
    codec: str
    timeout_seconds: float
    qc_rules: tuple[str, ...] = DEFAULT_QC_RULES
    extra_inputs: dict[str, bytes] = field(default_factory=dict)


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

    def plan(self, record: DeliveryRecord, source: Path) -> list[JobPlan]:
        """Turn the requested scenario into real job configuration.

        This is the only place in the measurement path that reads
        `record.fault_mode`. Everything after it observes consequences.
        """

        scenario = record.fault_mode
        plans: list[JobPlan] = []
        for index, spec in enumerate(record.specs):
            first = index == 0
            input_path = source
            codec = spec.video_codec
            timeout = 60.0
            qc_rules = tuple(record.qc_rules or DEFAULT_QC_RULES)
            extra: dict[str, bytes] = {}

            if first and scenario == "poison_input":
                # A real unreadable file on disk, not a flag.
                input_path = source.parent / "poison.bin"
                extra[input_path.name] = b"not a media file\x00\x01" * 64
            elif first and scenario == "wrong_codec":
                # A real encoder name this FFmpeg build does not have.
                codec = "encoder_that_does_not_exist"
            elif first and scenario == "timeout":
                # A real deadline the encode cannot meet.
                timeout = 0.001
            elif first and scenario == "qc_rule_change":
                # A real additional conformance rule this asset cannot satisfy,
                # exactly as a distributor tightening its spec would impose.
                if "textless_elements" not in qc_rules:
                    qc_rules = qc_rules + ("textless_elements",)

            plans.append(
                JobPlan(
                    spec=spec,
                    input_path=input_path,
                    output_path=source.parent / f"{spec.name}.mp4",
                    codec=codec,
                    timeout_seconds=timeout,
                    qc_rules=qc_rules,
                    extra_inputs=extra,
                )
            )
        return plans

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

    def _qc(self, plan: JobPlan) -> list[str]:
        """Evaluate the configured conformance rules against the decoded output."""

        failures: list[str] = []
        streams = self._probe(plan.output_path).get("streams", [])
        stream = streams[0] if streams else {}
        for rule in plan.qc_rules:
            if rule == "resolution":
                if stream.get("width") != plan.spec.width or stream.get("height") != plan.spec.height:
                    failures.append("resolution_mismatch")
            elif rule == "codec":
                expected_codec = "hevc" if plan.spec.video_codec == "libx265" else "h264"
                if stream.get("codec_name") != expected_codec:
                    failures.append("codec_mismatch")
            elif rule == "textless_elements":
                # The distributor requires a textless companion element beside
                # the rendition. Absence is observed on disk, not assumed.
                textless = plan.output_path.with_name(f"{plan.spec.name}.textless.mp4")
                if not textless.exists():
                    failures.append("missing_textless_element")
        return failures

    def _attempt(self, plan: JobPlan) -> tuple[int, str, bool]:
        """Run one FFmpeg attempt. Returns (exit_code, stderr, timed_out)."""

        try:
            process = self._run([
                self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(plan.input_path),
                "-vf", f"scale={plan.spec.width}:{plan.spec.height}", "-c:v", plan.codec,
                "-preset", "ultrafast", "-b:v", f"{plan.spec.video_bitrate_kbps}k", "-an",
                str(plan.output_path),
            ], timeout=plan.timeout_seconds)
            return process.returncode, process.stderr, False
        except subprocess.TimeoutExpired:
            return -1, "ffmpeg exceeded the real subprocess timeout", True

    def _transcode(self, record: DeliveryRecord, plan: JobPlan) -> JobResult:
        started = time.perf_counter()
        for name, payload in plan.extra_inputs.items():
            (plan.output_path.parent / name).write_bytes(payload)

        retries = 0
        failure_class: str | None = None
        exit_code = -1
        stderr = ""
        qc_failures: list[str] = []

        with stage_span(
            "transcode.rendition",
            delivery_id=record.delivery_id,
            spec=plan.spec.name,
            transform=f"{plan.spec.width}x{plan.spec.height}",
            encoder=plan.codec,
        ) as span:
            while True:
                exit_code, stderr, timed_out = self._attempt(plan)
                output_bytes = plan.output_path.stat().st_size if plan.output_path.exists() else 0
                failure_class = classify(
                    exit_code=exit_code,
                    stderr=stderr,
                    output_bytes=output_bytes,
                    timed_out=timed_out,
                )
                if failure_class is None or not is_retryable(failure_class) or retries >= 1:
                    break
                retries += 1
                event(
                    "rendition_retry",
                    delivery_id=record.delivery_id,
                    spec=plan.spec.name,
                    attempt=retries,
                    observed_class=failure_class,
                )

            if failure_class is None:
                with stage_span("qc.rendition", delivery_id=record.delivery_id, spec=plan.spec.name):
                    qc_failures = self._qc(plan)
                    failure_class = classify(
                        exit_code=exit_code,
                        stderr=stderr,
                        output_bytes=plan.output_path.stat().st_size if plan.output_path.exists() else 0,
                        timed_out=False,
                        qc_failures=qc_failures,
                    )

            span.set_attribute("exit_code", exit_code)
            span.set_attribute("retries", retries)
            span.set_attribute("observed_failure_class", failure_class or "none")

        duration = time.perf_counter() - started
        output_bytes = plan.output_path.stat().st_size if plan.output_path.exists() else 0
        status = "failed" if failure_class else "passed"
        JOB_DURATION.labels(spec=plan.spec.name, status=status).observe(duration)
        if failure_class:
            JOB_FAILURES.labels(failure_class=failure_class).inc()
        if retries:
            JOB_RETRIES.labels(spec=plan.spec.name).inc(retries)
        event(
            "rendition_complete",
            delivery_id=record.delivery_id,
            spec=plan.spec.name,
            status=status,
            duration_seconds=duration,
            exit_code=exit_code,
            retries=retries,
            observed_failure_class=failure_class,
            qc_rules_applied=list(plan.qc_rules),
            qc_failures=qc_failures,
            ffmpeg_stderr=stderr[-500:],
        )
        return JobResult(
            spec_name=plan.spec.name,
            status=status,
            duration_seconds=round(duration, 6),
            exit_code=exit_code,
            retries=retries,
            output_bytes=output_bytes,
            failure_class=failure_class,
            qc_failures=qc_failures,
        )

    def run(self, record: DeliveryRecord, limit: int | None = None) -> DeliveryRecord:
        """Encode outstanding renditions, optionally only the next `limit` of them.

        A facility works a delivery queue in waves rather than encoding every
        rendition at once, and that is also the only honest way to show the case
        that matters most: work still outstanding, nothing failed, and the
        remaining measured work no longer fitting before the contractual date.
        """

        directory = self.root / record.delivery_id
        directory.mkdir(parents=True, exist_ok=True)
        record.status = "running"
        record.pending_specs = len(record.specs)
        QUEUE_DEPTH.labels(delivery_id=record.delivery_id).set(record.pending_specs)
        # The pipeline span deliberately carries no scenario label and no title.
        # Both were previously readable by the agent, which turned diagnosis into
        # a lookup of the answer.
        with stage_span("delivery.pipeline", delivery_id=record.delivery_id) as pipeline_span:
            context = pipeline_span.get_span_context()
            if context.is_valid:
                record.last_trace_id = format(context.trace_id, "032x")
            source = self._source(directory, record.delivery_id)
            already_passed = {job.spec_name for job in record.jobs if job.status == "passed"}
            plans = [p for p in self.plan(record, source) if p.spec.name not in already_passed]
            if limit is not None:
                plans = plans[: max(0, limit)]
            jobs: list[JobResult] = []
            with ThreadPoolExecutor(max_workers=min(4, len(plans))) as executor:
                futures = [executor.submit(self._transcode, record, plan) for plan in plans]
                for future in as_completed(futures):
                    jobs.append(future.result())
                    record.pending_specs -= 1
                    QUEUE_DEPTH.labels(delivery_id=record.delivery_id).set(record.pending_specs)
            # Keep results for renditions this wave did not touch.
            encoded = {job.spec_name for job in jobs}
            record.jobs = sorted(
                [job for job in record.jobs if job.spec_name not in encoded] + jobs,
                key=lambda item: item.spec_name,
            )
            durations = sorted(job.duration_seconds for job in record.jobs)
            if durations:
                record.p95_seconds_per_spec = durations[min(len(durations) - 1, round(0.95 * len(durations)) - 1)]
            passed = {job.spec_name for job in record.jobs if job.status == "passed"}
            failed = [job for job in record.jobs if job.status == "failed"]
            # Anything not yet encoded successfully is still real outstanding
            # work: a failed rendition and one this wave never reached both
            # still have to happen before the date.
            record.pending_specs = len([spec for spec in record.specs if spec.name not in passed])
            QUEUE_DEPTH.labels(delivery_id=record.delivery_id).set(record.pending_specs)
            record.retry_penalty_seconds = sum(max(record.p95_seconds_per_spec, job.duration_seconds) for job in failed)
            with stage_span("package.manifest", delivery_id=record.delivery_id):
                manifest = {"delivery_id": record.delivery_id, "title": record.title, "generated_at": datetime.now(timezone.utc).isoformat(), "jobs": [job.model_dump() for job in record.jobs]}
                (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
                record.package_complete = record.pending_specs == 0 and not failed
            with stage_span("deliver.simulated_endpoint", delivery_id=record.delivery_id, simulated=True):
                record.simulated_delivery_accepted = record.package_complete
                event("simulated_delivery_result", delivery_id=record.delivery_id, accepted=record.simulated_delivery_accepted, reason="complete" if record.package_complete else "rendition_or_qc_failure")
        record.status = "healthy" if record.package_complete else "degraded"
        record.updated_at = datetime.now(timezone.utc)
        return record
