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


def test_every_agent_has_explicit_moderation_settings():
    """Left unset, these run on whatever the platform defaults to.

    Not all the text reaching these prompts is ours: a delivery title is typed
    by whoever created it, and Diagnose is asked to quote raw FFmpeg stderr. A
    production-ready agent should say what it blocks rather than inherit it.
    """

    import re
    from pathlib import Path

    from google.genai import types

    source = (Path(__file__).resolve().parents[1] / "slate_app" / "adk_app.py").read_text(
        encoding="utf-8"
    )
    # All three agents must be given the config, or the one that is not becomes
    # the way in.
    assert source.count("generate_content_config=safety") == 3

    expected = {
        types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        types.HarmCategory.HARM_CATEGORY_HARASSMENT,
        types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
    }
    named = {name for name in re.findall(r"HARM_CATEGORY_[A-Z_]+", source)}
    assert {category.name for category in expected} <= named

    assert "BLOCK_MEDIUM_AND_ABOVE" in source
    assert "BLOCK_NONE" not in source and "HarmBlockThreshold.OFF" not in source
