from slate_app.adk_app import _loki_query, _prometheus_queries


def test_agent_evidence_queries_use_real_metric_names_and_bound_delivery():
    queries = _prometheus_queries("del_abc123")
    assert queries == {
        "schedule_budget": 'slate_schedule_budget_seconds{delivery_id="del_abc123"}',
        "queue_depth": 'slate_queue_depth{delivery_id="del_abc123"}',
        "failures_by_class": "sum by (failure_class) (slate_job_failures_total)",
    }
    assert _loki_query("del_abc123").endswith('| delivery_id="del_abc123"')


def test_no_hallucinated_metric_namespace_survives():
    rendered = " ".join(_prometheus_queries("del_safe").values())
    assert "delivery_schedule_budget" not in rendered
    assert "delivery_queue_depth" not in rendered
    assert "delivery_failures_total" not in rendered


def test_loki_query_unwraps_the_otlp_body_before_filtering():
    """The OTLP log line is a JSON string inside `body`.

    A single `| json` stage exposes `body` and never `delivery_id`, so the old
    query returned zero rows on every run and the agents had no log evidence at
    all while appearing to have queried for it.
    """

    query = _loki_query("del_abc123")
    assert 'line_format "{{.body}}"' in query
    assert query.count("| json") == 2
    assert query.endswith('| delivery_id="del_abc123"')


def test_remediation_options_are_bound_to_actions_the_api_can_perform():
    from slate_app.models import REMEDIATION_ACTIONS, RemediationPlan

    schema = RemediationPlan.model_json_schema()
    option = schema["$defs"]["RemediationOption"]["properties"]["action"]
    assert set(option["enum"]) == set(REMEDIATION_ACTIONS)
