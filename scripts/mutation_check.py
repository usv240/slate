"""Break the code on purpose and prove the guards notice.

SLATE's central claim is that the failure class is recovered from FFmpeg's own
output and is not the injected scenario read back. Tests assert that. But a test
that protects a claim is worth nothing until you have watched it fail: the first
version of the classifier guard blanked every string constant before checking,
so `getattr(record, "fault_mode")` sailed through it and the guard reported
success while the leak was present.

This script applies each known regression as a real source edit, runs the test
that is supposed to catch it, and fails if the test passes. It restores every
file it touches, including on error.

Run it locally or in CI:

    python scripts/mutation_check.py
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLASSIFY = PROJECT_ROOT / "slate_app" / "classify.py"
PIPELINE = PROJECT_ROOT / "slate_app" / "pipeline.py"


@dataclass
class Mutation:
    name: str
    path: Path
    find: str
    replace: str
    guard: str
    why: str


MUTATIONS: list[Mutation] = [
    Mutation(
        name="classifier reads the scenario through an attribute",
        path=CLASSIFY,
        find="    if timed_out:",
        replace="    _leak = _record.fault_mode\n    if timed_out:",
        guard="tests/test_classify.py::test_the_classifier_cannot_see_the_injected_scenario",
        why="the class would become the injected label again",
    ),
    Mutation(
        name="classifier reads the scenario through a string literal",
        path=CLASSIFY,
        find="    if timed_out:",
        replace="    _leak = _kwargs['fault_mode']\n    if timed_out:",
        guard="tests/test_classify.py::test_the_classifier_cannot_see_the_injected_scenario",
        why="the original guard blanked string constants and missed exactly this",
    ),
    Mutation(
        name="measurement path reads the scenario",
        path=PIPELINE,
        find="        retries = 0\n",
        replace="        retries = 0\n        _leak = record.fault_mode\n",
        guard="tests/test_classify.py::test_the_measurement_path_never_reads_the_injected_scenario",
        why="observation must not be able to consult the injection",
    ),
    Mutation(
        name="pipeline span carries the scenario again",
        path=PIPELINE,
        find='with stage_span("delivery.pipeline", delivery_id=record.delivery_id) as pipeline_span:',
        replace=(
            'with stage_span("delivery.pipeline", delivery_id=record.delivery_id, '
            "fault_mode=record.fault_mode) as pipeline_span:"
        ),
        guard="tests/test_classify.py::test_the_pipeline_span_carries_no_scenario_or_title_attribute",
        why="this is the exact leak the Diagnose agent used to read off the trace",
    ),
    Mutation(
        name="classifier answers codec_fault for everything",
        path=CLASSIFY,
        find='    if timed_out:\n        return "timeout"',
        replace='    return "codec_fault"\n    if timed_out:\n        return "timeout"',
        guard="tests/test_classify.py",
        why="accuracy bought by labelling everything must not pass",
    ),
    Mutation(
        name="unrecognised failure silently defaults instead of admitting it",
        path=CLASSIFY,
        find="        return UNCLASSIFIED\n\n    if output_bytes <= 0:",
        replace='        return "codec_fault"\n\n    if output_bytes <= 0:',
        guard="tests/test_classify.py",
        why="an honest 'we do not know' is what makes the published number mean something",
    ),
]


def run_guard(guard: str) -> bool:
    """Return True when the guard fails, which is what a caught mutation looks like."""

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header", guard],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode != 0


def main() -> int:
    print("Mutation-testing SLATE's non-circularity guards")
    print("=" * 68)
    hollow: list[Mutation] = []

    for mutation in MUTATIONS:
        original = mutation.path.read_text(encoding="utf-8")
        if mutation.find not in original:
            print(f"[ERROR] {mutation.name}\n        anchor not found in {mutation.path.name}")
            return 2
        mutated = original.replace(mutation.find, mutation.replace, 1)
        mutation.path.write_text(mutated, encoding="utf-8")
        try:
            caught = run_guard(mutation.guard)
        finally:
            mutation.path.write_text(original, encoding="utf-8")

        if caught:
            print(f"[caught] {mutation.name}")
        else:
            hollow.append(mutation)
            print(f"[HOLLOW] {mutation.name}\n         {mutation.why}\n         guard: {mutation.guard}")

    print("=" * 68)
    print(f"{len(MUTATIONS) - len(hollow)}/{len(MUTATIONS)} mutations caught")
    if hollow:
        print("\nA guard that passes while the bug is present protects nothing.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
