from __future__ import annotations

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
from .telemetry import event, stage_span


MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
APP_NAME = "slate"

watch = LlmAgent(
    name="Watch",
    model=MODEL,
    instruction=(
        "The user message contains a deterministic jeopardy result which you may not alter. "
        "Read current schedule-budget, queue-depth, and failure metrics with query_prometheus "
        "through Grafana MCP. Report whether Grafana evidence corroborates the gate. Do not "
        "diagnose and do not create a verdict. Cite the exact query and returned series."
    ),
    tools=[query_prometheus],
    output_key="watch_evidence",
)

diagnose = LlmAgent(
    name="Diagnose",
    model=MODEL,
    instruction=(
        "Using {watch_evidence}, correlate real Loki logs and Tempo traces through Grafana MCP. "
        "Classify codec fault, poison input, timeout, capacity starvation, or QC rule change. "
        "Every claim must name the MCP result that supports it. If the evidence is insufficient, "
        "say uncertain; do not guess."
    ),
    tools=[query_loki, query_tempo],
    output_key="diagnosis",
)

remediate = LlmAgent(
    name="Remediate",
    model=MODEL,
    instruction=(
        "Using {watch_evidence} and {diagnosis}, propose three options with estimated schedule "
        "cost. Never execute, scale, requeue, annotate, or change a deadline. A delivery "
        "supervisor owns the decision."
    ),
    output_key="remediation_options",
)

root_agent = SequentialAgent(name="SlateDeliverySupervisor", sub_agents=[watch, diagnose, remediate])


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
    with stage_span("agent.investigation", delivery_id=delivery.delivery_id, session_id=session_id):
        async for agent_event in runner.run_async(
            user_id=operator_id,
            session_id=session_id,
            new_message=message,
        ):
            content = getattr(agent_event, "content", None)
            parts = getattr(content, "parts", None) or []
            text_parts = [part.text for part in parts if getattr(part, "text", None)]
            if text_parts:
                transcript.append(
                    {
                        "author": str(getattr(agent_event, "author", "agent")),
                        "text": "\n".join(text_parts),
                    }
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
    event(
        "agent_investigation_complete",
        delivery_id=delivery.delivery_id,
        session_id=session_id,
        model=MODEL,
        output_count=len([value for value in outputs.values() if value]),
    )
    return {
        "status": "completed",
        "session_id": session_id,
        "model": MODEL,
        "decision_source": "deterministic_gate",
        "observability_source": "grafana_mcp",
        "outputs": outputs,
        "transcript": transcript,
        "requires_human": True,
    }
