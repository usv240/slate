from fastapi.testclient import TestClient

from slate_app.main import app


def test_landing_page_exposes_truth_boundary_and_modes():
    response = TestClient(app).get("/")
    assert response.status_code == 200
    assert "FFmpeg execution and telemetry are real" in response.text
    assert "External delivery receiver is simulated" in response.text
    assert "Plain" in response.text
    assert "Technical" in response.text
    assert "Run 20s judge proof" in response.text
    assert "/v1/integrations/grafana/evidence" in response.text
    assert "Grafana control tower" in response.text


def test_landing_page_links_the_dashboard_that_actually_exists():
    """The provisioned dashboard UID is slate-delivery-slo.

    The page previously linked /d/slate-delivery/..., which renders Grafana's
    "Dashboard not found" page. It was the only partner-facing link on the page.
    """

    response = TestClient(app).get("/")
    assert "/d/slate-delivery-slo/" in response.text
    assert "/d/slate-delivery/slate-delivery-control-tower" not in response.text


def test_landing_page_offers_light_default_with_opt_in_dark():
    response = TestClient(app).get("/")
    assert 'data-theme="dark"' in response.text
    assert "prefers-reduced-motion" in response.text


def test_metrics_expose_pipeline_series():
    response = TestClient(app).get("/metrics")
    assert response.status_code == 200
    assert "slate_job_duration_seconds" in response.text
    assert "slate_schedule_budget_seconds" in response.text


def test_no_em_dash_reaches_the_page_or_anything_it_renders():
    """Punctuation is a house style decision, so it gets a guard like any other.

    The page is one file, but half of what it shows arrives from the API, so
    checking the HTML alone would pass while a served string still carried one.
    """

    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    surfaces = [root / "app" / "web" / "index.html"] + sorted((root / "slate_app").rglob("*.py"))
    offenders = [
        f"{path.relative_to(root).as_posix()}:{n}"
        for path in surfaces
        for n, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1)
        if "\u2014" in line or "&mdash;" in line
    ]
    assert not offenders, f"em dash on a user-visible surface: {offenders}"


def test_every_element_id_is_unique_and_every_nav_link_resolves():
    """A duplicate id is silent, and it cost us the whole page once.

    Adding `id="board"` to a section shadowed the existing `<div id="board">`,
    so `document.getElementById` returned the section and the board renderer
    called `replaceChildren()` on it, wiping the presets and the ladder builder.
    Nothing threw and every unit test stayed green; only the browser check saw
    it. This makes the same mistake fail in a plain test run.
    """

    import re
    from pathlib import Path

    page = (Path(__file__).resolve().parents[1] / "app" / "web" / "index.html").read_text(
        encoding="utf-8"
    )
    ids = re.findall(r'\sid="([^"]+)"', page)
    duplicates = sorted({value for value in ids if ids.count(value) > 1})
    assert not duplicates, f"duplicate element ids: {duplicates}"

    anchors = [target for target in re.findall(r'href="#([^"]+)"', page)]
    unresolved = [target for target in anchors if ids.count(target) != 1]
    assert not unresolved, f"in-page links with no unique target: {unresolved}"


def test_every_info_control_actually_explains_something():
    """An "i" that says nothing is worse than no "i" at all.

    The reader has already paid the cost of noticing it and moving the pointer,
    so an empty or placeholder tip spends their attention and returns nothing.
    """

    import re
    from pathlib import Path

    page = (Path(__file__).resolve().parents[1] / "app" / "web" / "index.html").read_text(
        encoding="utf-8"
    )

    static = re.findall(r'<span class="info[^"]*"[^>]*>', page)
    assert len(static) >= 8, "the static explanations disappeared"
    for tag in static:
        found = re.search(r'data-tip="([^"]*)"', tag)
        assert found, f"an info control carries no tip: {tag}"
        assert len(found.group(1)) > 40, f"tip too short to explain anything: {found.group(1)}"

    # The dynamic ones are built by info(), whose first argument is the tip.
    calls = re.findall(r"info\('([^']*)'", page)
    assert len(calls) >= 10, "the rendered explanations disappeared"
    for tip in calls:
        assert len(tip) > 40, f"tip too short to explain anything: {tip}"


def _miss_proof_config():
    """Read the zero-failure proof's own numbers out of the page."""

    import re
    from pathlib import Path

    page = (Path(__file__).resolve().parents[1] / "app" / "web" / "index.html").read_text(
        encoding="utf-8"
    )
    const = re.search(r"const MISS_WINDOW_S=(\d+), MISS_SPECS=(\d+);", page)
    return int(const.group(2)), float(const.group(1))


#: How much of the window is gone by wave three's gate evaluation, other than
#: the three encodes: creating the delivery, provisioning its Grafana alert
#: rule, two six second pauses and three round trips.
#:
#: Two bounds, not one, because there is no single honest value. The encodes are
#: charged at p95 below, and p95 is the slowest of the three samples rather than
#: their mean, so any model using it overstates the wall clock spent and
#: understates the window that is left. 11.5s is what the live proof implies if
#: each encode really cost p95; 22.5s is what it implies if they cost rather
#: less. The truth is in between and moves with the container, so the proof has
#: to hold at both ends and the tests assert both.
#:
#: An earlier version of this counted only the two pauses, was wrong by ten
#: seconds in the direction that hid the problem, and passed while the live
#: proof opened the gate one second before the contractual date.
PROOF_OVERHEAD_BOUNDS = (11.5, 22.5)

#: p95 per rendition, in seconds. This deployment has measured 3.9 to 5.6 for
#: 1920x1080 libx265 at 12000kbps on two vCPUs. The band is widened either side
#: of that, and deliberately not further: asserting the proof still works at
#: 2.5s would be asserting something about a machine nobody has run it on.
PROOF_P95_BAND = (3.5, 3.9, 4.5, 5.0, 5.6, 6.5)


def test_the_miss_proof_payload_is_one_the_api_will_accept():
    """It was not. The proof asked for twelve versions while the model capped
    them at eight, so every press returned 422 and the headline demonstration
    did nothing at all."""

    from datetime import datetime, timedelta, timezone

    from slate_app.models import CreateDelivery, RenditionSpec

    count, _ = _miss_proof_config()
    CreateDelivery(
        title="Aurora Line S2 - HDR delivery ladder",
        contractual_date=datetime.now(timezone.utc) + timedelta(seconds=40),
        penalty_tier="premiere",
        fault_mode="none",
        specs=[
            RenditionSpec(name=f"uhd{n}", width=1920, height=1080,
                          video_codec="libx265", video_bitrate_kbps=12000)
            for n in range(count)
        ],
    )


def test_the_miss_proof_opens_the_gate_at_every_speed_this_deployment_shows():
    """Whether the gate opened used to depend on how fast Cloud Run felt.

    At wave three the delivery has count-3 versions left, each costing the
    measured p95, against whatever remains of the window after three encodes and
    the fixed overhead. Both ends matter: too fast and the work still fits, too
    slow and the date has already gone, which is a different demonstration.
    """

    count, window = _miss_proof_config()
    for p95 in PROOF_P95_BAND:
        for overhead in PROOF_OVERHEAD_BOUNDS:
            work_left = (count - 3) * p95
            window_left = window - (3 * p95 + overhead)
            assert window_left > 0, f"p95 {p95}s, overhead {overhead}s: the date passes first"
            assert work_left > window_left, (
                f"p95 {p95}s, overhead {overhead}s: {work_left:.1f}s of work still fits in "
                f"{window_left:.1f}s of window, so the gate stays shut"
            )


def test_the_miss_the_proof_opens_is_one_added_capacity_can_still_save():
    """A warning nobody can act on is not worth firing.

    The proof ran against a forty second window and opened the gate every time,
    a second or so before the contractual date. Every threshold was correct and
    the demonstration was worthless: "what the warning buys you" could only
    answer "nothing recovers this", underneath the one case the product exists
    to show. The window is the fix, so the window is what this pins.
    """

    from slate_app.intervention import MAX_EXTRA_WORKERS

    count, window = _miss_proof_config()
    for p95 in PROOF_P95_BAND:
        for overhead in PROOF_OVERHEAD_BOUNDS:
            work_left = (count - 3) * p95
            window_left = window - (3 * p95 + overhead)
            best = work_left / (1 + MAX_EXTRA_WORKERS)
            assert best <= window_left, (
                f"p95 {p95}s, overhead {overhead}s: the gate opens with {window_left:.1f}s "
                f"left and even {MAX_EXTRA_WORKERS} extra workers need {best:.1f}s, so the "
                f"honest answer is that nothing recovers it"
            )


def test_the_page_and_the_end_to_end_checker_agree_on_the_window():
    """Two copies of the same number, and only one of them is what a judge presses."""

    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    count, window = _miss_proof_config()
    checker = (root / "scripts" / "e2e_check.py").read_text(encoding="utf-8")
    found = re.search(r"^MISS_WINDOW_S, MISS_SPECS = (\d+), (\d+)$", checker, re.M)
    assert (float(found.group(1)), int(found.group(2))) == (window, count)

    # The narration is read aloud on camera, so it is part of the claim.
    spoken = {"40": "forty", "50": "fifty", "55": "fifty-five", "60": "sixty"}[str(int(window))]
    for doc in ("README.md", "docs/DEMO-SCRIPT.md", "docs/DEVPOST-STORY.md"):
        text = (root / doc).read_text(encoding="utf-8").lower()
        assert f"{spoken} second" in text, f"{doc} still names a different window"
