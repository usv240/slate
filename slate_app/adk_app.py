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

from .grafana_mcp import (
    GrafanaMcp,
    GrafanaNotConfigured,
    loki_request,
    prometheus_request,
    tempo_request,
)
from .models import DeliveryRecord, JeopardyResult, RemediationPlan
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
    """LogQL that actually reaches SLATE's structured pipeline events.

    OTLP delivers the log line as a JSON *string* inside the `body` field, so a
    single `| json` stage exposes `body` and never `delivery_id`. The previous
    query therefore returned zero rows on every run, including in the recorded
    acceptance artifact, and the agents silently had no log evidence at all.
    Reparsing after `line_format` unwraps the body and yields the real fields.
    """

    return (
        '{service_name="slate"} | json | line_format "{{.body}}" | json '
        f'| delivery_id="{delivery_id}"'
    )


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
        logql = _loki_query(delivery.delivery_id)
        requests = [
            prometheus_request(queries["schedule_budget"]),
            prometheus_request(queries["queue_depth"]),
            prometheus_request(queries["failures_by_class"]),
            loki_request(logql),
        ]
        if delivery.last_trace_id:
            requests.append(tempo_request(delivery.last_trace_id))
        # One MCP session for the whole evidence sweep instead of one
        # subprocess and handshake per query.
        responses = await GrafanaMcp().call_many(requests)
        schedule, queue, failures, logs = responses[:4]
        trace_result: dict[str, Any] | None = responses[4] if delivery.last_trace_id else None
        result = {
            "delivery_id": delivery.delivery_id,
            "queries": queries,
            "prometheus": {
                "schedule_budget": schedule,
                "queue_depth": queue,
                "failures_by_class": failures,
            },
            "loki_query": logql,
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
            "A deterministic classifier already assigned the failure class from FFmpeg's own "
            "stderr, exit status and QC result; it is stated in the prompt and you cannot change "
            "it. Your job is corroboration, not classification. Using {watch_evidence} and only "
            "its bound Prometheus, Loki and Tempo evidence, quote the specific stderr text, exit "
            "code or failed QC rule that supports the stated class, and say plainly if the "
            "evidence does NOT support it or is missing. Never infer the cause from a delivery "
            "title, a scenario name or any label that merely restates the class."
        ),
        output_key="diagnosis",
    )
    remediate = LlmAgent(
        name="Remediate",
        model=MODEL,
        instruction=(
            "Using {watch_evidence} and {diagnosis}, produce three bounded remediation options. "
            "Every option must use one of the four actions SLATE can actually perform: "
            "requeue_safe (re-run the failed renditions with the corrected configuration), "
            "increase_workers (add one parallel worker), prioritize_contract (record contractual "
            "priority for a supervisor), escalate_deadline (record a deadline escalation request). "
            "Give each option an honest schedule cost in seconds and mark whether it is "
            "reversible. Cite the evidence for each. You never execute anything: a delivery "
            "supervisor approves, and only then does SLATE act."
        ),
        output_schema=RemediationPlan,
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
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
    observed = sorted({job.failure_class for job in delivery.jobs if job.failure_class})
    failed_qc = sorted({rule for job in delivery.jobs for rule in job.qc_failures})
    prompt = (
        f"Investigate delivery {delivery.delivery_id}. The deterministic gate verdict is "
        f"{gate.verdict}; its immutable evidence is {initial_state['deterministic_gate']}. "
        f"A deterministic classifier reading FFmpeg stderr, exit status and QC output assigned "
        f"the failure class(es) {observed or ['none']}"
        + (f" with failed QC rules {failed_qc}" if failed_qc else "")
        + ". That classification is fixed. Use Grafana MCP for every operational observation. "
        "Return corroborating evidence, a corroboration of the stated class, and human-only "
        "remediation options."
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
    raw_plan = state.get("remediation_options")
    plan: dict[str, Any] | None = None
    if raw_plan:
        try:
            candidate = json.loads(raw_plan) if isinstance(raw_plan, str) else raw_plan
            plan = RemediationPlan.model_validate(candidate).model_dump(mode="json")
        except Exception:
            # A malformed plan is reported as absent rather than rendered as if
            # it were an approved set of actions.
            plan = None
    outputs = {
        "watch": state.get("watch_evidence"),
        "diagnose": state.get("diagnosis"),
        "remediate": raw_plan,
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
        "classification_source": "deterministic_stderr_classifier",
        "observed_failure_classes": observed,
        "observability_source": "grafana_mcp",
        "bound_evidence": bound_evidence,
        "remediation_plan": plan,
        "outputs": outputs,
        "transcript": transcript,
        "requires_human": True,
    }
