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
    and alert when it drops below zero. It is created by SLATE, not by Gemini —
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
