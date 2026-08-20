import asyncio

import pytest

from slate_app import grafana_mcp


def test_resolve_exact_and_unique_proxied_tool():
    names = ["query_prometheus", "tempo_get-trace"]
    assert grafana_mcp.resolve_tool(names, "query_prometheus") == "query_prometheus"
    assert grafana_mcp.resolve_tool(names, "get-trace") == "tempo_get-trace"


def test_resolve_missing_tool_fails_closed():
    with pytest.raises(RuntimeError, match="unavailable"):
        grafana_mcp.resolve_tool(["query_prometheus"], "create_annotation")


def test_mcp_child_gets_only_grafana_credentials(monkeypatch):
    monkeypatch.setenv("GRAFANA_MCP_COMMAND", "mcp-grafana -t stdio")
    monkeypatch.setenv("GRAFANA_URL", "https://grafana.example")
    monkeypatch.setenv("GRAFANA_SERVICE_ACCOUNT_TOKEN", "secret-token")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "must-not-leak")
    parameters = grafana_mcp.GrafanaMcp().parameters
    assert parameters.env == {
        "GRAFANA_URL": "https://grafana.example",
        "GRAFANA_SERVICE_ACCOUNT_TOKEN": "secret-token",
    }


def test_prometheus_uses_official_schema(monkeypatch):
    captured = {}

    async def fake_call(self, tool, arguments):
        captured.update(tool=tool, arguments=arguments)
        return {"ok": True}

    monkeypatch.setenv("GRAFANA_MCP_COMMAND", "mcp-grafana -t stdio")
    monkeypatch.setenv("GRAFANA_PROMETHEUS_UID", "prom-uid")
    monkeypatch.setattr(grafana_mcp.GrafanaMcp, "call", fake_call)
    asyncio.run(grafana_mcp.query_prometheus("up"))
    assert captured["tool"] == "query_prometheus"
    assert captured["arguments"] == {
        "datasourceUid": "prom-uid",
        "expr": "up",
        "queryType": "instant",
        "startTime": "now-1h",
        "endTime": "now",
    }


def test_loki_uses_official_schema(monkeypatch):
    captured = {}

    async def fake_call(self, tool, arguments):
        captured.update(tool=tool, arguments=arguments)
        return {"ok": True}

    monkeypatch.setenv("GRAFANA_MCP_COMMAND", "mcp-grafana -t stdio")
    monkeypatch.setenv("GRAFANA_LOKI_UID", "loki-uid")
    monkeypatch.setattr(grafana_mcp.GrafanaMcp, "call", fake_call)
    asyncio.run(grafana_mcp.query_loki('{service_name="slate"}'))
    assert captured["tool"] == "query_loki_logs"
    assert captured["arguments"]["datasourceUid"] == "loki-uid"
    assert captured["arguments"]["logql"] == '{service_name="slate"}'


def test_tempo_uses_proxied_tool_schema(monkeypatch):
    captured = {}

    async def fake_call(self, tool, arguments):
        captured.update(tool=tool, arguments=arguments)
        return {"ok": True}

    monkeypatch.setenv("GRAFANA_MCP_COMMAND", "mcp-grafana -t stdio")
    monkeypatch.setenv("GRAFANA_TEMPO_UID", "tempo-uid")
    monkeypatch.setattr(grafana_mcp.GrafanaMcp, "call", fake_call)
    asyncio.run(grafana_mcp.query_tempo("a" * 32))
    assert captured == {
        "tool": "tempo_get-trace",
        "arguments": {"trace_id": "a" * 32, "datasourceUid": "tempo-uid"},
    }
