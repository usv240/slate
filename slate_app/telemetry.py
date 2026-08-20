from __future__ import annotations

import json
import logging
import os
import time
from contextlib import contextmanager
from typing import Iterator

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Gauge, Histogram


JOB_DURATION = Histogram("slate_job_duration_seconds", "Real ffmpeg job duration", ["spec", "status"])
JOB_FAILURES = Counter("slate_job_failures_total", "Real pipeline job failures", ["failure_class"])
JOB_RETRIES = Counter("slate_job_retries_total", "Real pipeline retries", ["spec"])
QUEUE_DEPTH = Gauge("slate_queue_depth", "Pending rendition jobs", ["delivery_id"])
SCHEDULE_BUDGET = Gauge("slate_schedule_budget_seconds", "Contract window minus measured work remaining", ["delivery_id"])


def configure_tracing() -> trace.Tracer:
    resource = Resource.create({"service.name": "slate", "deployment.environment": "judging"})
    provider = TracerProvider(resource=resource)
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


def configure_log_export() -> None:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return
    resource = Resource.create({"service.name": "slate", "deployment.environment": "judging"})
    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=f"{endpoint.rstrip('/')}/v1/logs"))
    )
    set_logger_provider(provider)
    LOGGER.addHandler(LoggingHandler(level=logging.INFO, logger_provider=provider))


configure_log_export()


def event(event_name: str, **fields: object) -> None:
    span_context = trace.get_current_span().get_span_context()
    correlation = {}
    if span_context.is_valid:
        correlation = {
            "trace_id": format(span_context.trace_id, "032x"),
            "span_id": format(span_context.span_id, "016x"),
        }
    LOGGER.info(
        json.dumps(
            {"event": event_name, "timestamp_unix": time.time(), **correlation, **fields},
            sort_keys=True,
        )
    )


@contextmanager
def stage_span(name: str, **attributes: object) -> Iterator[trace.Span]:
    with TRACER.start_as_current_span(name, attributes={key: value for key, value in attributes.items() if isinstance(value, (str, int, float, bool))}) as span:
        yield span
