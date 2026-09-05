from __future__ import annotations

import os
import shlex
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Iterable, Sequence

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .ai_telemetry import mcp_tool_span


class GrafanaNotConfigured(RuntimeError):
    pass


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise GrafanaNotConfigured(f"{name} is required; Grafana access cannot silently guess a datasource")
    return value


def resolve_tool(available: Iterable[str], requested: str) -> str:
    names = list(available)
    if requested in names:
        return requested
    # Grafana may expose proxied Tempo tools with a server prefix. Resolve only
    # a unique suffix; ambiguity fails closed rather than calling the wrong tool.
    matches = [name for name in names if name.endswith(requested)]
    if len(matches) == 1:
        return matches[0]
    raise RuntimeError(f"Grafana MCP tool '{requested}' unavailable; advertised tools: {', '.join(sorted(names))}")


class GrafanaMcp:
    """The only Grafana read/write path used by SLATE's agents."""

    def __init__(self) -> None:
        command = os.getenv("GRAFANA_MCP_COMMAND")
        if not command:
            raise GrafanaNotConfigured("GRAFANA_MCP_COMMAND is required; Grafana access cannot silently fall back")
        parts = shlex.split(command, posix=os.name != "nt")
        # mcp's stdio client intentionally forwards only a tiny default
        # environment. Pass the Grafana credentials explicitly, while keeping
        # unrelated Cloud Run and Google credentials out of the child process.
        child_env = {
            name: value
            for name in ("GRAFANA_URL", "GRAFANA_SERVICE_ACCOUNT_TOKEN")
            if (value := os.getenv(name))
        }
        self.parameters = StdioServerParameters(command=parts[0], args=parts[1:], env=child_env)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[ClientSession]:
        async with stdio_client(self.parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session

    @staticmethod
    def _shape(tool_name: str, resolved: str, result: Any) -> dict[str, Any]:
        return {
            "requested_tool": tool_name,
            "tool": resolved,
            "is_error": bool(getattr(result, "isError", False)),
            "content": [item.model_dump() for item in result.content],
        }

    async def call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        # Every MCP call is a span and a counter, so tool activity is visible in
        # Grafana next to the token cost of the agent that made it.
        with mcp_tool_span(server="grafana", tool=tool_name) as span:
            async with self.session() as session:
                advertised = await session.list_tools()
                resolved = resolve_tool((tool.name for tool in advertised.tools), tool_name)
                result = await session.call_tool(resolved, arguments)
            shaped = self._shape(tool_name, resolved, result)
            if span.is_recording():
                span.set_attribute("mcp.tool.resolved", resolved)
                span.set_attribute("mcp.tool.is_error", shaped["is_error"])
        return shaped

    async def call_many(self, requests: Sequence[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
        """Run several tools over one MCP session.

        Each `call` spawns an `mcp-grafana` subprocess and re-runs the protocol
        handshake, which measured about 1.2s per query. The agent's evidence step
        needs four or five tools at once, so it opens the session once and reuses
        it. Every tool is still counted and spanned individually.
        """

        results: list[dict[str, Any]] = []
        async with self.session() as session:
            advertised = await session.list_tools()
            names = [tool.name for tool in advertised.tools]
            for tool_name, arguments in requests:
                with mcp_tool_span(server="grafana", tool=tool_name) as span:
                    resolved = resolve_tool(names, tool_name)
                    result = await session.call_tool(resolved, arguments)
                    shaped = self._shape(tool_name, resolved, result)
                    if span.is_recording():
                        span.set_attribute("mcp.tool.resolved", resolved)
                        span.set_attribute("mcp.tool.is_error", shaped["is_error"])
                results.append(shaped)
        return results

    async def advertised_tools(self) -> list[str]:
        async with self.session() as session:
            advertised = await session.list_tools()
        return sorted(tool.name for tool in advertised.tools)


def prometheus_request(query: str) -> tuple[str, dict[str, Any]]:
    return (
        "query_prometheus",
        {
            "datasourceUid": _required("GRAFANA_PROMETHEUS_UID"),
            "expr": query,
            "queryType": "instant",
            "startTime": "now-1h",
            # mcp-grafana 1.1.0 validates endTime before applying the instant
            # query rule that marks it ignored; an explicit value avoids an
            # empty-time parser failure while remaining valid in newer builds.
            "endTime": "now",
        },
    )


def loki_request(query: str) -> tuple[str, dict[str, Any]]:
    return (
        "query_loki_logs",
        {
            "datasourceUid": _required("GRAFANA_LOKI_UID"),
            "logql": query,
            "startRfc3339": "now-1h",
            "limit": 50,
        },
    )


def tempo_request(trace_id: str) -> tuple[str, dict[str, Any]]:
    # Tempo tools are proxied and can be prefixed in the advertised MCP name.
    # The environment overrides both the exact suffix and argument name if a
    # particular Grafana stack exposes a different Tempo MCP schema.
    key = os.getenv("GRAFANA_TEMPO_TRACE_ID_KEY", "trace_id")
    return (
        os.getenv("GRAFANA_TEMPO_TOOL", "tempo_get-trace"),
        {key: trace_id, "datasourceUid": _required("GRAFANA_TEMPO_UID")},
    )


async def query_prometheus(query: str) -> dict[str, Any]:
    tool, arguments = prometheus_request(query)
    return await GrafanaMcp().call(tool, arguments)


async def query_loki(query: str) -> dict[str, Any]:
    tool, arguments = loki_request(query)
    return await GrafanaMcp().call(tool, arguments)


async def query_tempo(trace_id: str) -> dict[str, Any]:
    tool, arguments = tempo_request(trace_id)
    return await GrafanaMcp().call(tool, arguments)


async def write_annotation(text: str, tags: list[str]) -> dict[str, Any]:
    return await GrafanaMcp().call("create_annotation", {"text": text, "tags": tags})


def alert_rule_payload(delivery_id: str, title: str, contractual_date: str) -> dict[str, Any]:
    """Build the Grafana-managed alert rule for one delivery.

    The rule is the deterministic gate's first threshold expressed in Grafana's
    own alerting model: reduce the delivery's schedule budget to its last value
    and alert when it drops below zero. It is created by SLATE, not by Gemini:
    a model that cannot set a verdict must not be able to author the rule that
    represents it either.
    """

    prometheus_uid = _required("GRAFANA_PROMETHEUS_UID")
    return {
        "operation": "create",
        "title": f"SLATE schedule budget · {delivery_id}",
        "rule_group": "slate-delivery",
        "folder_uid": os.getenv("GRAFANA_ALERT_FOLDER_UID", "slate-media-delivery"),
        "condition": "C",
        "no_data_state": "NoData",
        "exec_err_state": "Alerting",
        "for": "1m",
        "org_id": 1,
        "labels": {"severity": "critical", "delivery_id": delivery_id, "managed_by": "slate"},
        "annotations": {
            "summary": f"Schedule budget for {delivery_id} is negative",
            "description": (
                f"Delivery {delivery_id} is contracted for {contractual_date}. This rule was "
                "provisioned through the official Grafana MCP server when the delivery was "
                "created. Remediation still requires human approval."
            ),
        },
        "data": [
            {
                "refId": "A",
                "datasourceUid": prometheus_uid,
                "relativeTimeRange": {"from": 600, "to": 0},
                "model": {"expr": f'slate_schedule_budget_seconds{{delivery_id="{delivery_id}"}}'},
            },
            {
                "refId": "B",
                "datasourceUid": "__expr__",
                "model": {"type": "reduce", "expression": "A", "reducer": "last"},
            },
            {
                "refId": "C",
                "datasourceUid": "__expr__",
                "model": {
                    "type": "threshold",
                    "expression": "B",
                    "conditions": [{"evaluator": {"type": "lt", "params": [0]}}],
                },
            },
        ],
    }


async def create_delivery_alert_rule(delivery_id: str, title: str, contractual_date: str) -> dict[str, Any]:
    """Provision a per-delivery alert rule through official Grafana MCP."""

    return await GrafanaMcp().call(
        "alerting_manage_rules", alert_rule_payload(delivery_id, title, contractual_date)
    )


async def delete_alert_rule(rule_uid: str) -> dict[str, Any]:
    return await GrafanaMcp().call("alerting_manage_rules", {"operation": "delete", "rule_uid": rule_uid})


#: Every tool SLATE calls, with why. Anything the server advertises that is not
#: here is a deliberate decline, reported by the evidence endpoint rather than
#: quietly absent.
TOOLS_USED: dict[str, str] = {
    "query_prometheus": "schedule budget, queue depth and failure counts for the agents and the health probe",
    "query_loki_logs": "the real FFmpeg stderr behind a failure class",
    "tempo_get-trace": "the per-delivery span tree, ingest through simulated delivery",
    "search_dashboards": "find the operator's dashboard and hand a human a link back to Grafana",
    "alerting_manage_rules": "provision and remove a Grafana-managed alert rule per delivery",
    "create_annotation": "record an approved remediation on the timeline, after human approval",
    "get_panel_image": "render the schedule-budget panel so Gemini can read the chart",
}

#: The three uses that are not the obvious way to reach for this server. The
#: first four tools above are what anyone would do with observability MCP; these
#: three are the reason this integration is worth looking at.
TOOLS_UNUSUAL: dict[str, str] = {
    "alerting_manage_rules": (
        "Alert rules are normally authored once by a human and left alone. SLATE writes one "
        "per delivery at creation, because the thing being watched is a contract, and every "
        "contract has a different date. The rule is deleted with the delivery."
    ),
    "create_annotation": (
        "The write is not the agent acting. It fires only after a human approves a remediation, "
        "so the Grafana timeline becomes the audit record of who decided what and when."
    ),
    "get_panel_image": (
        "MCP is used as a text API almost everywhere. Here Grafana renders the same panel the "
        "supervisor is looking at, MCP carries the PNG back, and Gemini reads the chart "
        "multimodally. The PNG it was given is shown beside the reading so you can check one "
        "against the other."
    ),
}

#: Every capability the track requirement names, and where SLATE answers it. The
#: wording of each capability is the requirement's own, so the mapping can be
#: checked line by line rather than taken on trust.
REQUIREMENT_COVERAGE: tuple[dict[str, str], ...] = (
    {
        "capability": "Query metrics (PromQL-compatible) for live system context",
        "status": "covered",
        "tool": "query_prometheus",
        "where": "Agent evidence sweep, the health probe, and a judge's own expression at /v1/analyze/promql",
    },
    {
        "capability": "Query logs (LogQL) for live system context",
        "status": "covered",
        "tool": "query_loki_logs",
        "where": "Diagnose quotes FFmpeg's own stderr from Loki rather than restating a label",
    },
    {
        "capability": "Query traces",
        "status": "covered",
        "tool": "tempo_get-trace",
        "where": "A media deliverable as a span tree, ingest through simulated delivery",
    },
    {
        "capability": "Search dashboards and generate links back to Grafana for human review",
        "status": "covered",
        "tool": "search_dashboards",
        "where": "/v1/integrations/grafana/dashboards returns the link and refuses to paraphrase the view",
    },
    {
        "capability": "Manage alerts",
        "status": "covered",
        "tool": "alerting_manage_rules",
        "where": "A Grafana-managed rule provisioned per delivery at creation and removed with it",
    },
    {
        "capability": "Correlate metrics, logs and traces during root-cause analysis",
        "status": "covered",
        "tool": "query_prometheus + query_loki_logs + tempo_get-trace, one MCP session",
        "where": "The evidence sweep binds Watch, Diagnose and Remediate to one session over all three signals",
    },
    {
        "capability": "Investigate incidents using Grafana IRM-related workflows",
        "status": "declined",
        "tool": "create_incident, list_incidents, Sift, OnCall",
        "where": "Grafana Cloud plugins. The rules direct unattended deployments to the self-hosted OSS server, and that choice is what removes IRM. On a Cloud stack this is the next step",
    },
    {
        "capability": "AI Observability: the agent's own LLM calls, token cost, latency and MCP tool activity",
        "status": "covered",
        "tool": "query_prometheus over gen_ai.* series",
        "where": "/v1/integrations/grafana/ai-observability reads the agent's own OpenTelemetry telemetry back through the same MCP server",
    },
)

#: Capabilities the requirement text names that SLATE does not use, and why.
TOOLS_DECLINED: dict[str, str] = {
    "incidents (create_incident, list_incidents, add_activity_to_incident)": (
        "Grafana IRM is a Grafana Cloud plugin. This stack is self-hosted OSS, which the rules "
        "permit for unattended deployments, so these tools are not available here. Opening an "
        "incident would be the right next step on a Cloud stack."
    ),
    "OnCall (list_oncall_schedules, get_current_oncall_users)": (
        "Also a Grafana Cloud plugin, and there is no real rota behind this deployment to report."
    ),
    "Sift (list_sift_investigations, get_sift_investigation)": (
        "Grafana Cloud only. SLATE's investigation is its own three-agent workflow over MCP evidence."
    ),
    "update_dashboard": (
        "The dashboard is provisioned from a file in this repository. Letting the agent rewrite it "
        "at runtime would make the operator's view something the model could change."
    ),
}


async def search_dashboards(query: str = "slate") -> dict[str, Any]:
    """Find dashboards through MCP so a human can be handed a link back to Grafana."""

    return await GrafanaMcp().call("search_dashboards", {"query": query})


async def get_panel_image(panel_id: int, *, hours: int = 6) -> dict[str, Any]:
    """Render a dashboard panel to PNG through MCP so Gemini can read the chart.

    Grafana renders the same panel a supervisor looks at, MCP carries the PNG
    back, and Gemini reads it multimodally. The reading is commentary on a
    picture: it is never allowed to become a verdict.
    """

    return await GrafanaMcp().call(
        "get_panel_image",
        {
            "dashboardUid": os.getenv("GRAFANA_DASHBOARD_UID", "slate-delivery-slo"),
            "panelId": panel_id,
            "width": 1000,
            "height": 500,
            "theme": "light",
            "timeRange": {"from": f"now-{hours}h", "to": "now"},
        },
    )
