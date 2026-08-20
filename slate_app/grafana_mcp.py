from __future__ import annotations

import json
import os
import shlex
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class GrafanaNotConfigured(RuntimeError):
    pass


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
            result = await session.call_tool(tool_name, arguments)
        return {"tool": tool_name, "is_error": bool(result.isError), "content": [item.model_dump() for item in result.content]}


async def query_prometheus(query: str) -> dict[str, Any]:
    return await GrafanaMcp().call(os.getenv("GRAFANA_PROM_TOOL", "query_prometheus"), {"query": query})


async def query_loki(query: str) -> dict[str, Any]:
    return await GrafanaMcp().call(os.getenv("GRAFANA_LOKI_TOOL", "query_loki_logs"), {"query": query})


async def query_tempo(trace_id: str) -> dict[str, Any]:
    return await GrafanaMcp().call(os.getenv("GRAFANA_TRACE_TOOL", "get_trace"), {"traceId": trace_id})


async def write_annotation(text: str, tags: list[str]) -> dict[str, Any]:
    return await GrafanaMcp().call(os.getenv("GRAFANA_ANNOTATION_TOOL", "create_annotation"), {"text": text, "tags": tags})
