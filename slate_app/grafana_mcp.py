from __future__ import annotations

import os
import shlex
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Iterable

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


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
        self.parameters = StdioServerParameters(command=parts[0], args=parts[1:], env=None)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[ClientSession]:
        async with stdio_client(self.parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session

    async def call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        async with self.session() as session:
            advertised = await session.list_tools()
            resolved = resolve_tool((tool.name for tool in advertised.tools), tool_name)
            result = await session.call_tool(resolved, arguments)
        return {
            "requested_tool": tool_name,
            "tool": resolved,
            "is_error": bool(getattr(result, "isError", False)),
            "content": [item.model_dump() for item in result.content],
        }


async def query_prometheus(query: str) -> dict[str, Any]:
    return await GrafanaMcp().call(
        "query_prometheus",
        {
            "datasourceUid": _required("GRAFANA_PROMETHEUS_UID"),
            "expr": query,
            "queryType": "instant",
            "startTime": "now-1h",
        },
    )


async def query_loki(query: str) -> dict[str, Any]:
    return await GrafanaMcp().call(
        "query_loki_logs",
        {
            "datasourceUid": _required("GRAFANA_LOKI_UID"),
            "logql": query,
            "startRfc3339": "now-1h",
            "limit": 50,
        },
    )


async def query_tempo(trace_id: str) -> dict[str, Any]:
    # Tempo tools are proxied and can be prefixed in the advertised MCP name.
    # The environment overrides both the exact suffix and argument name if a
    # particular Grafana stack exposes a different Tempo MCP schema.
    key = os.getenv("GRAFANA_TEMPO_TRACE_ID_KEY", "traceID")
    return await GrafanaMcp().call(os.getenv("GRAFANA_TEMPO_TOOL", "tempo_get-trace"), {key: trace_id})


async def write_annotation(text: str, tags: list[str]) -> dict[str, Any]:
    return await GrafanaMcp().call("create_annotation", {"text": text, "tags": tags})
