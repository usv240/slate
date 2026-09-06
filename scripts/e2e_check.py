"""Drive every scenario against a running deployment and report what broke.

The unit suite proves the pieces. This proves the thing a judge actually
touches: real HTTP against the real service, with real FFmpeg behind it and the
real Grafana MCP server behind that. Several defects this session were invisible
to the unit tests and obvious the first time somebody pressed a button, so this
presses the buttons.

    python scripts/e2e_check.py
    python scripts/e2e_check.py --url http://localhost:8080
    python scripts/e2e_check.py --quick        # skip the two slow proofs

It leaves the board recording-ready unless it fails partway, and exits non-zero
if any scenario fails.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_URL = "https://slate-delivery-slo-109051079423.us-central1.run.app"
#: The zero-failure proof's own numbers. Must match MISS_WINDOW_S and MISS_SPECS
#: in app/web/index.html, because this checks the button a judge actually presses;
#: tests/test_web.py fails the build if the two drift apart.
MISS_WINDOW_S, MISS_SPECS = 60, 16

RESULTS: list[tuple[str, bool, str]] = []


#: Set once a key is issued. An anonymous caller gets four investigations per
#: ten minutes, and a failed one still spends a slot, so a full run of this
#: checker would rate-limit itself halfway through the agent section.
API_KEY: str | None = None


def call(base, path, method="GET", body=None, timeout=240):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(base + path, data=data, method=method)
    request.add_header("content-type", "application/json")
    if API_KEY:
        request.add_header("authorization", "Bearer " + API_KEY)
    if data is None and method == "POST":
        request.add_header("content-length", "0")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return response.status, (json.loads(raw) if raw.startswith(("{", "[")) else raw)
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", "replace")
        try:
            return error.code, json.loads(raw)
        except json.JSONDecodeError:
            return error.code, raw


def check(name, passed, detail=""):
    RESULTS.append((name, bool(passed), detail))
    print(f"  {'PASS' if passed else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    return bool(passed)


def ladder(count, *, codec="libx264", width=320, height=180, kbps=300):
    return [
        {"name": f"spec{n}", "width": width, "height": height,
         "video_codec": codec, "video_bitrate_kbps": kbps}
        for n in range(count)
    ]


def in_seconds(seconds):
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def section(title):
    print(f"\n{title}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--quick", action="store_true", help="skip the two slow FFmpeg proofs")
    args = parser.parse_args()
    base = args.url.rstrip("/")
    print(f"end-to-end check against {base}")

    global API_KEY
    status, issued = call(base, "/v1/keys", "POST")
    API_KEY = (issued.get("data") or {}).get("api_key") if isinstance(issued, dict) else None
    check("a judge key can be issued without signing up", status in (200, 201) and bool(API_KEY),
          f"HTTP {status}")

    # --- the service is actually up ---------------------------------------
    section("runtime")
    status, health = call(base, "/health")
    integrations = (health or {}).get("integrations", {}) if isinstance(health, dict) else {}
    check("health returns 200", status == 200)
    for name in ("google_vertex", "grafana_mcp", "state_store", "otlp_export", "agent_runtime_ready"):
        check(f"integration {name}", integrations.get(name) is True)
    check("delivery receiver is declared simulated",
          isinstance(health, dict) and health.get("delivery_endpoint") == "simulated")

    status, page = call(base, "/")
    check("page serves", status == 200 and isinstance(page, str) and len(page) > 20000)
    if isinstance(page, str):
        check("page carries no em dash", chr(8212) not in page and "&mdash;" not in page)
        check("navbar is in demo order",
              page.find('href="#blindspot"') < page.find('href="#board"') < page.find('href="#partner"'))

    # --- the board resets and keeps itself in date ------------------------
    section("board lifecycle")
    status, reset = call(base, "/v1/board/reset", "POST")
    check("board reset returns 200", status == 200)
    status, listing = call(base, "/v1/deliveries")
    rows = listing.get("data", []) if isinstance(listing, dict) else []
    fixtures = [r for r in rows if r.get("fixture_window_hours") is not None]
    check("reset leaves exactly the three fixtures", len(rows) == 3 and len(fixtures) == 3,
          f"{len(rows)} on board")
    now = datetime.now(timezone.utc)
    live = all(datetime.fromisoformat(r["contractual_date"].replace("Z", "+00:00")) > now for r in fixtures)
    check("every fixture date is in the future", live)
    check("every fixture is healthy", all(r["status"] in {"healthy", "recovered"} for r in fixtures))
    status, again = call(base, "/v1/board/fixtures")
    rolled = again.get("data", {}).get("rolled_forward", []) if isinstance(again, dict) else None
    check("fixture refresh is idempotent", rolled == [], f"rolled {rolled}")

    # --- input validation --------------------------------------------------
    section("input validation")
    status, _ = call(base, "/v1/deliveries", "POST", {
        "title": "too many", "contractual_date": in_seconds(600),
        "penalty_tier": "standard", "fault_mode": "none", "specs": ladder(17)})
    check("17 versions is refused", status == 422, f"HTTP {status}")
    status, _ = call(base, "/v1/deliveries", "POST", {
        "title": "at the cap", "contractual_date": in_seconds(600),
        "penalty_tier": "standard", "fault_mode": "none", "specs": ladder(16)})
    check("16 versions is accepted", status == 201, f"HTTP {status}")
    capped = _
    status, _ = call(base, "/v1/deliveries", "POST", {
        "title": "absurd resolution", "contractual_date": in_seconds(600),
        "penalty_tier": "standard", "fault_mode": "none",
        "specs": ladder(1, width=99999, height=99999)})
    check("an out of range resolution is refused, not clamped", status == 422, f"HTTP {status}")
    status, _ = call(base, "/v1/deliveries/does_not_exist/intervention")
    check("an unknown delivery is a 404", status == 404, f"HTTP {status}")
    if isinstance(capped, dict) and capped.get("data"):
        call(base, f"/v1/deliveries/{capped['data']['delivery_id']}", "DELETE")

    # --- presets are exactly what the API accepts -------------------------
    section("bring your own")
    status, presets = call(base, "/v1/presets")
    listed = presets.get("data", {}).get("presets", []) if isinstance(presets, dict) else []
    check("three presets are offered", len(listed) == 3, f"{len(listed)} found")
    if listed:
        preset_id = listed[0]["id"]
        status, body = call(base, f"/v1/presets/{preset_id}")
        check("a preset downloads as JSON", status == 200 and isinstance(body, dict))
        payload = body.get("data", body) if isinstance(body, dict) else {}
        payload = payload.get("body", payload)
        status, created = call(base, "/v1/deliveries", "POST", payload)
        check("the downloaded preset posts back unchanged", status == 201, f"HTTP {status}")
        if status == 201:
            call(base, f"/v1/deliveries/{created['data']['delivery_id']}", "DELETE")

    status, promql = call(base, "/v1/analyze/promql", "POST", {"expr": "up"})
    check("a judge's own PromQL runs through MCP", status == 200, f"HTTP {status}")
    status, bad = call(base, "/v1/analyze/promql", "POST", {"expr": "this is not promql {{"})
    check("a bad expression returns the server's own error, not a crash",
          status in (200, 400, 422), f"HTTP {status}")

    # --- the Grafana integration ------------------------------------------
    section("grafana mcp")
    status, ev = call(base, "/v1/integrations/grafana/evidence")
    data = ev.get("data", {}) if isinstance(ev, dict) else {}
    used = data.get("tools_used", {})
    check("evidence endpoint answers", status == 200)
    check("server advertises its tool count", isinstance(data.get("advertised_tool_count"), int))
    check("all seven tools confirmed advertised live",
          len(used) == 7 and all(v.get("advertised") for v in used.values()),
          f"{sum(1 for v in used.values() if v.get('advertised'))}/{len(used)}")
    status, inv = call(base, "/v1/integrations/grafana/inventory")
    coverage = inv.get("data", {}).get("requirement_coverage", []) if isinstance(inv, dict) else []
    covered = [c for c in coverage if c["status"] == "covered"]
    check("requirement coverage map is published", len(coverage) == 8, f"{len(coverage)} rows")
    check("seven of eight capabilities covered", len(covered) == 7, f"{len(covered)} covered")
    check("three unusual uses are named",
          len(inv.get("data", {}).get("tools_unusual", {})) == 3)
    status, dash = call(base, "/v1/integrations/grafana/dashboards")
    check("dashboard search returns a link for a human", status == 200, f"HTTP {status}")
    status, obs = call(base, "/v1/integrations/grafana/ai-observability")
    check("the agents' own telemetry reads back through MCP", status == 200, f"HTTP {status}")
    status, panel = call(base, "/v1/integrations/grafana/panel-reading?panel_id=2&hours=6")
    reading = panel.get("data", {}) if isinstance(panel, dict) else {}
    check("grafana renders a panel and gemini reads it", status == 200, f"HTTP {status}")
    if status == 200:
        check("the PNG it was given is returned too", bool(reading.get("image_data_uri")))
        check("the reading is commentary, not a verdict",
              reading.get("decision_source") == "deterministic_gate",
              str(reading.get("decision_source")))

    # --- the failure path, end to end -------------------------------------
    section("failure path")
    status, proof = call(base, "/v1/deliveries", "POST", {
        "title": "E2E: codec fault", "contractual_date": in_seconds(12),
        "penalty_tier": "premiere", "fault_mode": "wrong_codec", "specs": ladder(1, width=640, height=360, kbps=800)})
    proof_id = proof["data"]["delivery_id"] if status == 201 else None
    check("a delivery provisions its own Grafana alert rule",
          bool((proof.get("data", {}).get("alert_rule") or {}).get("provisioned")))
    verdict = None
    for attempt in range(1, 6):
        status, run = call(base, f"/v1/deliveries/{proof_id}/run", "POST")
        verdict = run.get("data", {}).get("status")
        if verdict == "at_risk":
            break
        time.sleep(5.4)
    check("the gate opens only after sustained burn", verdict == "at_risk", f"after {attempt} runs")
    check("one blip is not enough", attempt >= 3, f"opened on run {attempt}")

    status, jeopardy = call(base, f"/v1/jeopardy/{proof_id}")
    gate = jeopardy.get("data", {}).get("gate", {}) if isinstance(jeopardy, dict) else {}
    check("all three gate conditions are reported", len(gate.get("passed", [])) == 3)
    status, delivery = call(base, "/v1/deliveries")
    record = next((r for r in delivery.get("data", []) if r["delivery_id"] == proof_id), {})
    classes = {j.get("failure_class") for j in record.get("jobs", [])}
    check("the class comes back as codec_fault", "codec_fault" in classes, str(classes))
    check("no emitted result carries the injected scenario name",
          "wrong_codec" not in json.dumps(record.get("jobs", [])))

    # --- the agents --------------------------------------------------------
    section("agents")
    status, report = call(base, f"/v1/jeopardy/{proof_id}/investigate", "POST",
                          {"operator_id": "e2e"})
    if status >= 500:
        print("       (first attempt returned 5xx, retrying once as the page does)")
        status, report = call(base, f"/v1/jeopardy/{proof_id}/investigate", "POST",
                              {"operator_id": "e2e"})
    result = report.get("data", {}) if isinstance(report, dict) else {}
    outputs = result.get("outputs") or {}
    check("investigation completes", status == 200 and result.get("status") == "completed",
          f"HTTP {status}")
    check("all three agents produced output", sorted(outputs) == ["diagnose", "remediate", "watch"],
          str(sorted(outputs)))
    check("diagnose quotes FFmpeg's own stderr", "Unknown encoder" in (outputs.get("diagnose") or ""))
    check("the verdict came from the gate, not the model",
          result.get("decision_source") == "deterministic_gate", str(result.get("decision_source")))
    check("the class came from the classifier, not the model",
          result.get("classification_source") == "deterministic_stderr_classifier",
          str(result.get("classification_source")))

    healthy = next((r["delivery_id"] for r in delivery.get("data", []) if r["status"] == "healthy"), None)
    if healthy:
        status, abstain = call(base, f"/v1/jeopardy/{healthy}/investigate", "POST", {"operator_id": "e2e"})
        body = abstain.get("data", {}) if isinstance(abstain, dict) else {}
        check("a healthy delivery gets an abstention, not an investigation",
              status == 200 and body.get("status") == "abstained", f"HTTP {status}")
        check("the abstention calls no model", body.get("model_called") is False,
              str(body.get("model_called")))

    # --- human approval ----------------------------------------------------
    section("human approval")
    plan = result.get("remediation_plan") or {}
    proposed = {o["action"] for o in plan.get("options", [])} if plan else set()
    never = next((a for a in ("requeue_safe", "increase_workers", "prioritize_contract",
                              "escalate_deadline") if a not in proposed), None)
    if never:
        status, refused = call(base, f"/v1/deliveries/{proof_id}/remediation", "POST",
                               {"action": never, "operator_id": "e2e", "approved": True})
        check("an action the agent did not propose is refused with 409", status == 409,
              f"HTTP {status} for {never}")
    if "requeue_safe" in proposed:
        status, approved = call(base, f"/v1/deliveries/{proof_id}/remediation", "POST",
                                {"action": "requeue_safe", "operator_id": "e2e", "approved": True})
        approval = approved.get("data", {}) if isinstance(approved, dict) else {}
        check("an approved action executes", status == 200 and approval.get("executed") is True)
        check("approval writes a Grafana annotation",
              bool((approval.get("grafana_annotation") or {}).get("written", True)))
        status, rerun = call(base, f"/v1/deliveries/{proof_id}/run", "POST")
        check("re-running after approval recovers the delivery",
              rerun.get("data", {}).get("status") == "recovered",
              str(rerun.get("data", {}).get("status")))

    status, md = call(base, f"/v1/deliveries/{proof_id}/report")
    check("a supervisor can download a report", status == 200 and "Delivery report" in str(md))
    status, _ = call(base, f"/v1/deliveries/{proof_id}", "DELETE")
    check("a delivery can be removed", status == 200)

    # --- the claim the whole product rests on -----------------------------
    if not args.quick:
        section("the miss with zero failures")
        status, miss = call(base, "/v1/deliveries", "POST", {
            "title": "E2E: zero failure miss", "contractual_date": in_seconds(MISS_WINDOW_S),
            "penalty_tier": "premiere", "fault_mode": "none",
            "specs": ladder(MISS_SPECS, codec="libx265", width=1920, height=1080, kbps=12000)})
        miss_id = miss["data"]["delivery_id"] if status == 201 else None
        check(f"{MISS_SPECS} heavy versions are accepted", status == 201, f"HTTP {status}")
        verdicts, failures, window_left = [], 0, 0.0
        for wave in (1, 2, 3):
            status, run = call(base, f"/v1/deliveries/{miss_id}/run?batch=1", "POST")
            jeop, rec = run.get("jeopardy", {}), run.get("data", {})
            failures = sum(1 for j in rec.get("jobs", []) if j["status"] == "failed")
            verdicts.append(jeop.get("verdict"))
            window_left = jeop.get("delivery_window_seconds", 0)
            print(f"       wave {wave}: {failures} failures, work "
                  f"{jeop.get('work_remaining_seconds', 0):.1f}s vs window "
                  f"{jeop.get('delivery_window_seconds', 0):.1f}s -> {jeop.get('verdict')}")
            if wave < 3:
                time.sleep(6)
        check("nothing failed at any point", failures == 0, f"{failures} failures")
        check("the gate opened anyway", verdicts[-1] == "at_risk", str(verdicts))
        check("and not before it should", verdicts[0] == "healthy", str(verdicts))
        # The README claims the gate fires with roughly twenty seconds still on
        # the clock. It once fired with 1.4s left, which is technically before
        # the date and worth nothing to anybody. Assert the claim, not the sign.
        check("it fires with time still on the clock", window_left >= 8,
              f"{window_left:.1f}s of window left when the gate opened")

        status, det = call(base, "/v1/evaluation/detectors")
        summary = det.get("data", {}).get("summary", {}) if isinstance(det, dict) else {}
        check("the comparison records an invisible miss", summary.get("invisible_miss", 0) >= 1,
              f"{summary.get('invisible_miss')} found")
        card = next((c for c in det.get("data", {}).get("comparisons", [])
                     if c["disagreement"] == "invisible_miss"), {})
        detectors = {d["name"]: d["fired"] for d in card.get("detectors", [])}
        check("a failure alert is silent on it", detectors.get("any_failure") is False)
        check("a deadline check is silent on it", detectors.get("deadline_passed") is False)
        check("only the gate fires", detectors.get("slate_gate") is True)

        status, buys = call(base, f"/v1/deliveries/{miss_id}/intervention")
        outcome = buys.get("data", {}) if isinstance(buys, dict) else {}
        check("what the warning buys is reported", status == 200)
        check("doing nothing misses the date", outcome.get("doing_nothing_lands") is False)
        save = outcome.get("cheapest_save") or {}
        check("and more capacity would save it", outcome.get("recoverable") is True,
              f"+{save.get('added_workers')} workers lands it with "
              f"{save.get('slack_seconds')}s to spare" if save else
              f"nothing recovers {outcome.get('pending_specs')} x "
              f"{outcome.get('p95_seconds_per_spec')}s in "
              f"{outcome.get('window_seconds')}s")
        call(base, f"/v1/deliveries/{miss_id}", "DELETE")

    # --- leave the board ready --------------------------------------------
    section("cleanup")
    status, _ = call(base, "/v1/board/reset", "POST")
    check("board reset for recording", status == 200)

    failed = [name for name, ok, _ in RESULTS if not ok]
    print("\n" + "=" * 68)
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} scenarios passed")
    for name in failed:
        print(f"  FAILED: {name}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
