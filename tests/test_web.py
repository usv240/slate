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
