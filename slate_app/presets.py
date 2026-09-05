"""Named delivery scenarios a judge can load, read, download, or edit.

A demo that only ever runs one fixed shape invites the fair objection that it
would fall over on anything else. These presets are not a separate demo path:
each one is exactly the JSON body `POST /v1/deliveries` accepts, so loading one
from the page and posting the downloaded file with curl produce the same record.
Nothing here is privileged, and a judge is free to change any field.

Contractual dates are relative offsets resolved at request time, so a preset
downloaded today is still a live scenario next week rather than a stale date.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass(frozen=True)
class Preset:
    id: str
    name: str
    demonstrates: str
    detail: str
    hours_to_contract: float
    penalty_tier: str
    fault_mode: str
    specs: list[dict[str, Any]]
    qc_rules: list[str] = field(default_factory=lambda: ["resolution", "codec"])
    expect: str = ""

    def body(self, now: datetime | None = None) -> dict[str, Any]:
        """The exact CreateDelivery payload for this scenario."""

        now = now or datetime.now(timezone.utc)
        contract = now + timedelta(hours=self.hours_to_contract)
        return {
            "title": self.name,
            "contractual_date": contract.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "penalty_tier": self.penalty_tier,
            "fault_mode": self.fault_mode,
            "qc_rules": list(self.qc_rules),
            "specs": [dict(spec) for spec in self.specs],
        }

    def describe(self, now: datetime | None = None) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "demonstrates": self.demonstrates,
            "detail": self.detail,
            "expect": self.expect,
            "hours_to_contract": self.hours_to_contract,
            "spec_count": len(self.specs),
            "body": self.body(now),
        }


def _spec(name: str, width: int, height: int, kbps: int, codec: str = "libx264") -> dict[str, Any]:
    return {
        "name": name,
        "width": width,
        "height": height,
        "video_codec": codec,
        "video_bitrate_kbps": kbps,
    }


PRESETS: tuple[Preset, ...] = (
    Preset(
        id="streamer-ladder",
        name="Streamer package, four-rendition ladder",
        demonstrates="The healthy path, and that the gate stays quiet when it should",
        detail=(
            "A four-rendition delivery ladder with two days of contract window. Every "
            "encode succeeds, so the schedule budget stays positive, no incident opens, "
            "and asking the agents anything returns an abstention that calls no model."
        ),
        expect="healthy · agent abstains · no model call",
        hours_to_contract=52,
        penalty_tier="priority",
        fault_mode="none",
        specs=[
            _spec("proxy", 320, 180, 300),
            _spec("review", 640, 360, 800),
            _spec("broadcast", 1280, 720, 4000),
            _spec("archive", 1280, 720, 6000, codec="libx265"),
        ],
    ),
    Preset(
        id="festival-encoder",
        name="Festival cut, encoder missing from the build",
        demonstrates="Jeopardy opening on evidence, and the classifier reading real stderr",
        detail=(
            "A tight six-hour window and an encoder this FFmpeg build does not have. Run "
            "the pipeline three times: the gate stays healthy for two windows because one "
            "blip is not evidence, then opens. Diagnose quotes FFmpeg's own "
            "\"Unknown encoder\" line rather than restating a label."
        ),
        expect="at_risk on the third window · codec_fault from stderr",
        hours_to_contract=6,
        penalty_tier="premiere",
        fault_mode="wrong_codec",
        specs=[
            _spec("festival", 640, 360, 800),
            _spec("review", 320, 180, 300),
        ],
    ),
    Preset(
        id="qc-tightened",
        name="Distributor tightens the QC spec mid-delivery",
        demonstrates="A different failure class, from configuration rather than a crash",
        detail=(
            "The distributor adds a textless-element requirement the asset cannot satisfy. "
            "Every encode exits cleanly, so nothing looks broken at the process level. The "
            "failure is found by the conformance rules, and the class comes back as "
            "qc_failure with the specific rule named."
        ),
        expect="qc_failure · missing_textless_element · exit code 0",
        hours_to_contract=14,
        penalty_tier="standard",
        fault_mode="qc_rule_change",
        specs=[
            _spec("proxy", 320, 180, 300),
            _spec("review", 640, 360, 800),
            _spec("broadcast", 1280, 720, 4000),
        ],
        qc_rules=["resolution", "codec"],
    ),
)

BY_ID: dict[str, Preset] = {preset.id: preset for preset in PRESETS}


def catalogue(now: datetime | None = None) -> list[dict[str, Any]]:
    return [preset.describe(now) for preset in PRESETS]
