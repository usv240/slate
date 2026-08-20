from __future__ import annotations

import json
import logging
import os
import time
from contextlib import contextmanager
from typing import Iterator

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Gauge, Histogram


JOB_DURATION = Histogram("slate_job_duration_seconds", "Real ffmpeg job duration", ["spec", "status"])
JOB_FAILURES = Counter("slate_job_failures_total", "Real pipeline job failures", ["failure_class"])
JOB_RETRIES = Counter("slate_job_retries_total", "Real pipeline retries", ["spec"])
QUEUE_DEPTH = Gauge("slate_queue_depth", "Pending rendition jobs", ["delivery_id"])
SCHEDULE_BUDGET = Gauge("slate_schedule_budget_seconds", "Contract window minus measured work remaining", ["delivery_id"])


def configure_tracing() -> trace.Tracer:
    provider = TracerProvider()
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        exporter = OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces")
        provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    metrics.set_meter_provider(MeterProvider())
    return trace.get_tracer("slate.pipeline")


TRACER = configure_tracing()
LOGGER = logging.getLogger("slate.pipeline")
LOGGER.setLevel(logging.INFO)


def event(event_name: str, **fields: object) -> None:
    LOGGER.info(json.dumps({"event": event_name, "timestamp_unix": time.time(), **fields}, sort_keys=True))


@contextmanager
def stage_span(name: str, **attributes: object) -> Iterator[trace.Span]:
    with TRACER.start_as_current_span(name, attributes={key: value for key, value in attributes.items() if isinstance(value, (str, int, float, bool))}) as span:
        yield span
