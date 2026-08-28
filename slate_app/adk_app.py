from __future__ import annotations

import asyncio
import json
import os
import uuid
from typing import Any

from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from .grafana_mcp import GrafanaNotConfigured, query_loki, query_prometheus, query_tempo
from .models import DeliveryRecord, JeopardyResult
from .ai_telemetry import genai_span, record_usage
from .telemetry import event, stage_span


MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
APP_NAME = "slate"

class AgentRuntimeNotConfigured(RuntimeError):
    pass


def validate_agent_runtime() -> None:
    google_required = ("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION")
    missing_google = [name for name in google_required if not os.getenv(name)]
    vertex_enabled = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in {"1", "true", "yes"}
    if not vertex_enabled:
        missing_google.append("GOOGLE_GENAI_USE_VERTEXAI=TRUE")
    if missing_google:
        raise AgentRuntimeNotConfigured(f"Missing Google Vertex configuration: {', '.join(missing_google)}")
    grafana_required = (
        "GRAFANA_MCP_COMMAND",
        "GRAFANA_PROMETHEUS_UID",
        "GRAFANA_LOKI_UID",
        "GRAFANA_TEMPO_UID",
    )
    missing_grafana = [name for name in grafana_required if not os.getenv(name)]
    if missing_grafana:
        raise GrafanaNotConfigured(f"Missing Grafana MCP configuration: {', '.join(missing_grafana)}")


def _prometheus_queries(delivery_id: str) -> dict[str, str]:
    return {
        "schedule_budget": f'slate_schedule_budget_seconds{{delivery_id="{delivery_id}"}}',
        "queue_depth": f'slate_queue_depth{{delivery_id="{delivery_id}"}}',
        "failures_by_class": "sum by (failure_class) (slate_job_failures_total)",
    }


def _loki_query(delivery_id: str) -> str:
    return f'{{service_name="slate"}} | json | delivery_id="{delivery_id}"'


async def run_investigation(
    delivery: DeliveryRecord,
    gate: JeopardyResult,
    *,
    operator_id: str,
) -> dict[str, Any]:
    """Run the real three-agent ADK workflow after the deterministic gate passes.

    This function is deliberately absent from the gate module: Gemini explains and
    proposes; it cannot create jeopardy or approve remediation.
    """

    validate_agent_runtime()
    bound_evidence: dict[str, Any] = {}

    async def get_bound_grafana_evidence() -> dict[str, Any]:
        """Return exact Grafana MCP evidence bound to this delivery and trace."""

        queries = _prometheus_queries(delivery.delivery_id)
        schedule, queue, failures, logs = await asyncio.gather(
            query_prometheus(queries["schedule_budget"]),
            query_prometheus(queries["queue_depth"]),
            query_prometheus(queries["failures_by_class"]),
            query_loki(_loki_query(delivery.delivery_id)),
        )
        trace_result: dict[str, Any] | None = None
        if delivery.last_trace_id:
            trace_result = await query_tempo(delivery.last_trace_id)
        result = {
            "delivery_id": delivery.delivery_id,
            "queries": queries,
            "prometheus": {
                "schedule_budget": schedule,
                "queue_depth": queue,
                "failures_by_class": failures,
            },
            "loki_query": _loki_query(delivery.delivery_id),
            "loki": logs,
            "trace_id": delivery.last_trace_id,
            "tempo": trace_result,
        }
        bound_evidence.update(result)
        return result

    watch = LlmAgent(
        name="Watch",
        model=MODEL,
        instruction=(
            "The deterministic jeopardy result is immutable. You MUST call "
            "get_bound_grafana_evidence exactly once. Report whether the returned schedule "
            "budget and queue evidence corroborate the gate. Cite exact query names and observed "
            "values. Do not diagnose and do not create or change a verdict."
        ),
        tools=[get_bound_grafana_evidence],
        output_key="watch_evidence",
    )
    diagnose = LlmAgent(
        name="Diagnose",
        model=MODEL,
        instruction=(
            "Using {watch_evidence} and only its bound Prometheus, Loki, and Tempo evidence, "
            "classify codec fault, poison input, timeout, capacity starvation, or QC rule change. "
            "Name the specific log or trace evidence for the classification. If evidence is "
            "insufficient, say uncertain; do not guess and do not change the gate."
        ),
        output_key="diagnosis",
    )
    remediate = LlmAgent(
        name="Remediate",
        model=MODEL,
        instruction=(
            "Using {watch_evidence} and {diagnosis}, propose exactly three bounded options with "
            "estimated schedule cost. Never execute, scale, requeue, annotate, or change a "
            "deadline. State that a delivery supervisor owns the decision."
        ),
        output_key="remediation_options",
    )
    root_agent = SequentialAgent(
        name="SlateDeliverySupervisor",
        sub_agents=[watch, diagnose, remediate],
    )
    session_id = f"investigation_{uuid.uuid4().hex[:12]}"
    session_service = InMemorySessionService()
    initial_state = {
        "delivery_id": delivery.delivery_id,
        "operator_id": operator_id,
        "deterministic_gate": json.dumps(gate.model_dump(mode="json"), sort_keys=True),
    }
    await session_service.create_session(
        app_name=APP_NAME,
        user_id=operator_id,
        session_id=session_id,
        state=initial_state,
    )
    runner = Runner(app_name=APP_NAME, agent=root_agent, session_service=session_service)
    prompt = (
        f"Investigate delivery {delivery.delivery_id}. The deterministic gate verdict is "
        f"{gate.verdict}; its immutable evidence is {initial_state['deterministic_gate']}. "
        "Use Grafana MCP for every operational observation. Return evidence, diagnosis, and "
        "human-only remediation options."
    )
    message = types.Content(role="user", parts=[types.Part(text=prompt)])
    transcript: list[dict[str, str]] = []
    usage_by_agent: dict[str, dict[str, int]] = {}
    with stage_span("agent.investigation", delivery_id=delivery.delivery_id, session_id=session_id):
        # One GenAI span per investigation, with per-sub-agent token usage recorded
        # as each agent reports it, so Grafana can be asked what this cost.
        with genai_span(
            agent=APP_NAME,
            model=MODEL,
            delivery_id=delivery.delivery_id,
            session_id=session_id,
        ) as span:
            async for agent_event in runner.run_async(
                user_id=operator_id,
                session_id=session_id,
                new_message=message,
            ):
                author = str(getattr(agent_event, "author", "agent"))
                usage = getattr(agent_event, "usage_metadata", None)
                if usage is not None:
                    counts = record_usage(span, agent=author, model=MODEL, usage=usage)
                    running = usage_by_agent.setdefault(author, {"input": 0, "output": 0, "total": 0})
                    for key, value in counts.items():
                        running[key] += value
                content = getattr(agent_event, "content", None)
                parts = getattr(content, "parts", None) or []
                text_parts = [part.text for part in parts if getattr(part, "text", None)]
                if text_parts:
                    transcript.append({"author": author, "text": chr(10).join(text_parts)})
            span.set_attribute(
                "gen_ai.usage.input_tokens", sum(v["input"] for v in usage_by_agent.values())
            )
            span.set_attribute(
                "gen_ai.usage.output_tokens", sum(v["output"] for v in usage_by_agent.values())
            )
    completed = await session_service.get_session(
        app_name=APP_NAME,
        user_id=operator_id,
        session_id=session_id,
    )
    state = completed.state if completed else {}
    outputs = {
        "watch": state.get("watch_evidence"),
        "diagnose": state.get("diagnosis"),
        "remediate": state.get("remediation_options"),
    }
    if not bound_evidence:
        raise RuntimeError("Watch did not retrieve its request-bound Grafana MCP evidence")
    if any(not value for value in outputs.values()):
        raise RuntimeError("The ADK workflow did not produce all three governed outputs")
    event(
        "agent_investigation_complete",
        delivery_id=delivery.delivery_id,
        session_id=session_id,
        model=MODEL,
        output_count=len([value for value in outputs.values() if value]),
        input_tokens=sum(item["input"] for item in usage_by_agent.values()),
        output_tokens=sum(item["output"] for item in usage_by_agent.values()),
    )
    return {
        "status": "completed",
        "token_usage": {
            "by_agent": usage_by_agent,
            "input_tokens": sum(item["input"] for item in usage_by_agent.values()),
            "output_tokens": sum(item["output"] for item in usage_by_agent.values()),
            "note": "recorded as OpenTelemetry gen_ai.* attributes and Prometheus counters",
        },
        "session_id": session_id,
        "model": MODEL,
        "decision_source": "deterministic_gate",
        "observability_source": "grafana_mcp",
        "bound_evidence": bound_evidence,
        "outputs": outputs,
        "transcript": transcript,
        "requires_human": True,
    }
