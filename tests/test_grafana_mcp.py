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


def test_every_tool_we_claim_to_use_is_reachable_through_one_helper():
    """The inventory must describe the code, not aspirations.

    `tools_used` is published on the evidence endpoint as a statement about what
    SLATE calls. If a name drifts out of the code the statement becomes a claim
    nobody checks, so it is checked here.
    """

    import inspect

    from slate_app import grafana_mcp

    source = inspect.getsource(grafana_mcp)
    for tool in grafana_mcp.TOOLS_USED:
        assert tool in source, f"{tool} is advertised in TOOLS_USED but never called"


def test_declines_carry_a_reason_rather_than_being_absent():
    from slate_app.grafana_mcp import TOOLS_DECLINED

    assert TOOLS_DECLINED, "a declined capability should be stated, not silently missing"
    for capability, reason in TOOLS_DECLINED.items():
        assert len(reason) > 60, f"{capability} needs a real reason, not a shrug"


def test_dashboard_search_is_a_read_that_ends_at_a_human():
    from fastapi.testclient import TestClient

    from slate_app.main import app

    # Without Grafana configured it must say so rather than invent dashboards.
    response = TestClient(app).get("/v1/integrations/grafana/dashboards")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "grafana_mcp_not_configured"
