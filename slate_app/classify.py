"""Deterministic failure classification from observed evidence only.

This module is the reason SLATE's fault diagnosis can be trusted.

An earlier build labelled every failure with the fault that had been *injected*
into the run. The metric label, the trace attribute and therefore the agent's
"diagnosis" were all the answer key written back out, and the benchmark that
scored them reported 100% accuracy for a tautology.

Nothing here may see the injected scenario. `classify` receives only what a real
operator would have: the process exit code, whether our own timeout killed it,
how many bytes came out, the QC rules that failed, and FFmpeg's stderr. A guard
test asserts that the string `fault_mode` never appears in this file.

Ordering matters: the first matching signature wins, and the specific encoder
and demuxer signatures are tested before the generic ones.
"""

from __future__ import annotations

import re


#: Ordered (pattern, class) pairs. First match wins.
_SIGNATURES: tuple[tuple[re.Pattern[str], str], ...] = (
    # The requested encoder does not exist in this FFmpeg build, or exists but
    # cannot be initialised for the requested parameters.
    (
        re.compile(
            r"unknown encoder|encoder not found|automatic encoder selection failed"
            r"|cannot determine format of input|no encoder found for codec"
            r"|encoder initialization failed|error initializing output stream",
            re.IGNORECASE,
        ),
        "codec_fault",
    ),
    # The input could not be demuxed: truncated, corrupt, or not media at all.
    (
        re.compile(
            r"invalid data found when processing input|moov atom not found"
            r"|error opening input|no such file or directory"
            r"|end of file|does not contain any stream|invalid argument"
            r"|header missing|could not find codec parameters",
            re.IGNORECASE,
        ),
        "poison_input",
    ),
)

#: Returned when a process failed but no signature matched. This is an honest
#: "we do not know", not a default guess, and the evaluation counts it as a miss.
UNCLASSIFIED = "transcode_failure"


def classify(
    *,
    exit_code: int,
    stderr: str,
    output_bytes: int,
    timed_out: bool,
    qc_failures: list[str] | None = None,
) -> str | None:
    """Return the observed failure class, or None when the job genuinely passed.

    Args:
        exit_code: the real process exit status. Values differ across platforms,
            so it is used only to decide *whether* something failed, never which.
        stderr: FFmpeg's own diagnostic output. This is the primary signal.
        output_bytes: size of the produced rendition; zero after a clean exit is
            itself a failure.
        timed_out: True when our own subprocess timeout killed the process. This
            is an observation about our execution, not an injected label.
        qc_failures: names of conformance rules that failed on a decoded output.
    """

    if timed_out:
        return "timeout"

    if exit_code != 0:
        for pattern, failure_class in _SIGNATURES:
            if pattern.search(stderr or ""):
                return failure_class
        return UNCLASSIFIED

    if output_bytes <= 0:
        # FFmpeg reported success and wrote nothing. Treat it as a transcode
        # failure rather than inventing a cause.
        return UNCLASSIFIED

    if qc_failures:
        return "qc_failure"

    return None


def is_retryable(failure_class: str | None) -> bool:
    """Only genuinely transient classes are retried.

    A missing encoder and an unreadable input fail identically on every attempt;
    retrying them would inflate the retry metric without learning anything. A
    timeout or an unclassified failure can be transient, so each gets one retry.
    """

    return failure_class in {"timeout", UNCLASSIFIED}
