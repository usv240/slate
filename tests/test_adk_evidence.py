from slate_app.adk_app import _loki_query, _prometheus_queries


def test_agent_evidence_queries_use_real_metric_names_and_bound_delivery():
    queries = _prometheus_queries("del_abc123")
    assert queries == {
        "schedule_budget": 'slate_schedule_budget_seconds{delivery_id="del_abc123"}',
        "queue_depth": 'slate_queue_depth{delivery_id="del_abc123"}',
        "failures_by_class": "sum by (failure_class) (slate_job_failures_total)",
    }
    assert _loki_query("del_abc123") == (
        '{service_name="slate"} | json | delivery_id="del_abc123"'
    )


def test_no_hallucinated_metric_namespace_survives():
    rendered = " ".join(_prometheus_queries("del_safe").values())
    assert "delivery_schedule_budget" not in rendered
    assert "delivery_queue_depth" not in rendered
    assert "delivery_failures_total" not in rendered
