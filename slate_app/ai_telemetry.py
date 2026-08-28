"""OpenTelemetry GenAI instrumentation: Grafana observes the agent, not just the pipeline.

SLATE's agents watch the delivery pipeline through Grafana. This module closes
the loop by emitting the agent's own behaviour back into the same stack, using
the OpenTelemetry GenAI semantic conventions that Grafana Cloud AI Observability
consumes: model, operation, token usage, latency, and MCP tool activity.

The result is that the same Grafana MCP server the agent uses to read delivery
metrics can also be asked what the agent cost and how long it took -- token
usage per investigation, latency per sub-agent, and how many MCP tool calls each
investigation actually made.

Attribute names follow the `gen_ai.*` conventions rather than invented ones, so
the data is readable by any OTel-native AI observability backend and not just by
a dashboard written for this project.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Iterator

from opentelemetry import trace
from prometheus_client import Counter, Histogram

from .telemetry import TRACER


GEN_AI_SYSTEM = "vertex_ai"

# Prometheus mirrors the span data so it is queryable through the same Grafana
# MCP server the agents already use, without needing a trace lookup first.
LLM_TOKENS = Counter(
    "slate_gen_ai_tokens_total",
    "Tokens consumed by the ADK agents on Vertex AI",
    ["model", "agent", "token_type"],
)
LLM_LATENCY = Histogram(
    "slate_gen_ai_operation_duration_seconds",
    "Duration of a GenAI operation",
    ["model", "agent", "operation"],
)
MCP_CALLS = Counter(
    "slate_mcp_tool_calls_total",
    "MCP tool invocations made while serving a request",
    ["server", "tool", "outcome"],
)
MCP_LATENCY = Histogram(
    "slate_mcp_tool_duration_seconds",
    "Duration of one MCP tool invocation",
    ["server", "tool"],
)


@contextmanager
def genai_span(
    *, agent: str, model: str, operation: str = "invoke_agent", **extra: object
) -> Iterator[trace.Span]:
    """Span for one agent invocation, named and attributed per GenAI conventions."""
    attributes: dict[str, Any] = {
        "gen_ai.system": GEN_AI_SYSTEM,
        "gen_ai.operation.name": operation,
        "gen_ai.request.model": model,
        "gen_ai.agent.name": agent,
    }
    for key, value in extra.items():
        if isinstance(value, (str, int, float, bool)):
            attributes[key] = value
    started = time.perf_counter()
    with TRACER.start_as_current_span(f"{operation} {agent}", attributes=attributes) as span:
        try:
            yield span
        finally:
            LLM_LATENCY.labels(model=model, agent=agent, operation=operation).observe(
                time.perf_counter() - started
            )


def record_usage(span: trace.Span | None, *, agent: str, model: str, usage: Any) -> dict[str, int]:
    """Attach token usage to the span and to Prometheus.

    ADK surfaces usage metadata inconsistently across event types, so missing
    counts are reported as zero rather than guessed.
    """
    counts = {
        "input": int(getattr(usage, "prompt_token_count", 0) or 0),
        "output": int(getattr(usage, "candidates_token_count", 0) or 0),
        "total": int(getattr(usage, "total_token_count", 0) or 0),
    }
    if span is not None and span.is_recording():
        span.set_attribute("gen_ai.usage.input_tokens", counts["input"])
        span.set_attribute("gen_ai.usage.output_tokens", counts["output"])
        span.set_attribute("gen_ai.response.model", model)
    for token_type in ("input", "output"):
        if counts[token_type]:
            LLM_TOKENS.labels(model=model, agent=agent, token_type=token_type).inc(counts[token_type])
    return counts


@contextmanager
def mcp_tool_span(*, server: str, tool: str) -> Iterator[trace.Span]:
    """Span for one MCP tool call, so tool activity is visible next to LLM cost."""
    started = time.perf_counter()
    outcome = "error"
    with TRACER.start_as_current_span(
        f"mcp.{tool}",
        attributes={"mcp.server": server, "mcp.tool": tool, "gen_ai.tool.name": tool},
    ) as span:
        try:
            yield span
            outcome = "ok"
        finally:
            elapsed = time.perf_counter() - started
            MCP_LATENCY.labels(server=server, tool=tool).observe(elapsed)
            MCP_CALLS.labels(server=server, tool=tool, outcome=outcome).inc()
