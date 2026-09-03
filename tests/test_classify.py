"""The failure class must come from observed output, never from the injection.

An earlier build derived the metric label and the trace attribute from the fault
that had been injected, so the agent's "diagnosis" was the answer key read back
and the benchmark scored a tautology at 100%. These tests exist to make that
regression impossible to reintroduce quietly.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from slate_app import pipeline as pipeline_module
from slate_app.classify import UNCLASSIFIED, classify, is_retryable


UNKNOWN_ENCODER = (
    "[vost#0:0 @ 0x5630a1c2f400] Unknown encoder 'encoder_that_does_not_exist'\n"
    "Error opening output file /tmp/slate/proxy.mp4.\n"
)
POISON_INPUT = (
    "[in#0 @ 0x55e8d9b0f2c0] Error opening input: Invalid data found when processing input\n"
    "Error opening input file /tmp/slate/poison.bin.\n"
)


def test_unknown_encoder_is_a_codec_fault():
    assert classify(exit_code=8, stderr=UNKNOWN_ENCODER, output_bytes=0, timed_out=False) == "codec_fault"


def test_undemuxable_input_is_a_poison_input():
    assert classify(exit_code=183, stderr=POISON_INPUT, output_bytes=0, timed_out=False) == "poison_input"


def test_our_own_timeout_is_a_timeout_regardless_of_stderr():
    assert classify(exit_code=-1, stderr=UNKNOWN_ENCODER, output_bytes=0, timed_out=True) == "timeout"


def test_unrecognised_failure_is_reported_as_unclassified_not_guessed():
    observed = classify(exit_code=1, stderr="something nobody has seen before", output_bytes=0, timed_out=False)
    assert observed == UNCLASSIFIED


def test_clean_run_with_output_and_no_qc_failures_passes():
    assert classify(exit_code=0, stderr="", output_bytes=127826, timed_out=False, qc_failures=[]) is None


def test_conformance_failure_on_a_good_encode_is_a_qc_failure():
    observed = classify(
        exit_code=0,
        stderr="",
        output_bytes=127826,
        timed_out=False,
        qc_failures=["missing_textless_element"],
    )
    assert observed == "qc_failure"


def test_clean_exit_with_no_output_is_not_reported_as_success():
    assert classify(exit_code=0, stderr="", output_bytes=0, timed_out=False) == UNCLASSIFIED


def test_only_transient_classes_are_retried():
    assert is_retryable("timeout") is True
    assert is_retryable(UNCLASSIFIED) is True
    assert is_retryable("codec_fault") is False
    assert is_retryable("poison_input") is False
    assert is_retryable(None) is False


def test_the_classifier_cannot_see_the_injected_scenario():
    source = Path(inspect.getfile(classify)).read_text(encoding="utf-8")
    # The docstring names the field it must never read; strip comments and
    # docstrings so the guard checks executable code rather than prose.
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            node.value = ""
    assert "fault_mode" not in ast.unparse(tree)


@pytest.mark.parametrize("function_name", ["_transcode", "_attempt", "_qc", "run"])
def test_the_measurement_path_never_reads_the_injected_scenario(function_name):
    """Only `plan` may consult the scenario, and only to build real configuration."""

    source = Path(inspect.getfile(pipeline_module)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    target = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    )
    assert "fault_mode" not in ast.unparse(target), (
        f"{function_name} reads the injected scenario; the observed failure class would "
        "become the answer key again"
    )


def test_plan_is_the_single_place_the_scenario_is_consumed():
    source = Path(inspect.getfile(pipeline_module)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    plan = next(
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "plan"
    )
    assert "fault_mode" in ast.unparse(plan)


def test_the_pipeline_span_carries_no_scenario_or_title_attribute():
    """The trace is what a judge and the Diagnose agent both read."""

    source = Path(inspect.getfile(pipeline_module)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    run = next(
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "run"
    )
    body = ast.unparse(run)
    span_call = body[body.index("stage_span('delivery.pipeline'") :].split(")")[0]
    assert "fault_mode" not in span_call
    assert "title" not in span_call
