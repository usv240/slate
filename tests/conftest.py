"""Make the FFmpeg proofs unskippable where they are supposed to run.

The tests that matter most — the five scenarios classified from real FFmpeg
output — skip themselves when FFmpeg is absent. That is right on a developer
machine and dangerous in CI: if the FFmpeg install step ever broke, every one of
them would skip, the run would still be green, and the badge would be asserting
a proof that had not executed.

With `SLATE_REQUIRE_FULL_SUITE=1` a skip is a failure, and the report names each
skipped test so the cause is obvious rather than buried in a count.
"""

from __future__ import annotations

import os

import pytest


def _required() -> bool:
    return os.getenv("SLATE_REQUIRE_FULL_SUITE", "").lower() in {"1", "true", "yes"}


@pytest.hookimpl(trylast=True)
def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:
    if not _required():
        return
    skipped = terminalreporter.stats.get("skipped", [])
    if not skipped:
        return
    terminalreporter.write_sep("=", "SKIPPED TESTS ARE NOT ALLOWED HERE", red=True)
    for report in skipped:
        reason = ""
        if isinstance(getattr(report, "longrepr", None), tuple) and len(report.longrepr) == 3:
            reason = report.longrepr[2]
        terminalreporter.write_line(f"  {report.nodeid}  {reason}")
    terminalreporter.write_line(
        "\nSLATE_REQUIRE_FULL_SUITE is set, so every test must actually run. "
        "A skipped proof is not a passing proof."
    )
    terminalreporter._session.exitstatus = pytest.ExitCode.TESTS_FAILED
    if hasattr(config, "_slate_skip_failure"):
        return
    config._slate_skip_failure = True


def pytest_sessionfinish(session, exitstatus) -> None:
    if not _required():
        return
    skipped = session.config.pluginmanager.get_plugin("terminalreporter")
    if skipped is None:
        return
    if skipped.stats.get("skipped"):
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
