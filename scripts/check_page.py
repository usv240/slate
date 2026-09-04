"""Drive the real page in a real browser and prove it actually initialised.

Every unit test can pass while the page is dead. A single syntax error or a
throw at init detaches every listener, and what a judge sees is an empty board,
a spinner that never resolves, and controls that do nothing. It happened here
twice: both times the tests were green and the page was broken.

Two layers, because they catch different things:

1. `node --check` on the page's script. Catches the syntax errors that stop the
   whole block from parsing.
2. A headless browser load against a real server, asserting the DOM the page is
   supposed to build. Catches a throw at init, which parses fine.

    python scripts/check_page.py
    python scripts/check_page.py --keep-going   # report every failure, not the first
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE = PROJECT_ROOT / "app" / "web" / "index.html"

BROWSERS = (
    "google-chrome",
    "chromium-browser",
    "chromium",
    "msedge",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)

#: Substrings the rendered DOM must contain once the page has initialised.
#: Each is something only JavaScript can put there.
REQUIRED = (
    ('class="preset"', "preset scenario cards were never rendered"),
    ('class="specrow"', "the custom rendition builder never rendered its rows"),
    ('class="chip"', "the PromQL example chips never rendered"),
    ("contractual deliveries", "the summary bar is missing"),
)

#: Substrings that must be gone once the page has initialised.
FORBIDDEN = (
    ("Loading&hellip;", "the demo panel never resolved"),
    ("Loading…", "the demo panel never resolved"),
    ("Checking…", "the demo panel never resolved"),
    ("Waiting for API", "the board never loaded from the API"),
)


def find_browser() -> str | None:
    for candidate in BROWSERS:
        resolved = shutil.which(candidate) if os.sep not in candidate else (
            candidate if Path(candidate).exists() else None
        )
        if resolved:
            return resolved
    return None


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def extract_script() -> str:
    html = PAGE.read_text(encoding="utf-8")
    blocks = re.findall(r"<script>(.*?)</script>", html, re.S)
    if not blocks:
        raise SystemExit("no inline script found in the page")
    return blocks[-1]


def check_syntax(failures: list[str]) -> None:
    node = shutil.which("node")
    if node is None:
        failures.append("node is not installed, so the page script was never syntax checked")
        return
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as handle:
        handle.write(extract_script())
        path = handle.name
    try:
        result = subprocess.run([node, "--check", path], capture_output=True, text=True)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip().splitlines()
            failures.append("the page script does not parse:\n    " + "\n    ".join(detail[:6]))
        else:
            print("[ok] page script parses")
    finally:
        os.unlink(path)


def check_render(failures: list[str]) -> None:
    browser = find_browser()
    if browser is None:
        failures.append("no headless browser found, so the page was never actually loaded")
        return

    port = free_port()
    env = {**os.environ, "SLATE_WORK_ROOT": tempfile.mkdtemp(prefix="slate-page-")}
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "slate_app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"{base}/v1/presets", timeout=2).read()
                break
            except (urllib.error.URLError, ConnectionError, OSError):
                time.sleep(0.5)
        else:
            failures.append("the server never became ready, so the page could not be loaded")
            return

        # A slower machine can finish the page after a short virtual-time budget
        # expires, so a single impatient load is a flaky check rather than a real
        # one. Give it progressively longer and only report the last attempt: a
        # genuinely dead page never renders, however long you wait.
        attempt_failures: list[str] = []
        for budget in (10000, 25000, 45000):
            attempt_failures = []
            with tempfile.TemporaryDirectory(prefix="slate-profile-") as profile:
                result = subprocess.run(
                    [
                        browser,
                        "--headless=new",
                        "--disable-gpu",
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        f"--virtual-time-budget={budget}",
                        f"--user-data-dir={profile}",
                        "--dump-dom",
                        base + "/",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=240,
                )
            dom = result.stdout
            if len(dom) < 500:
                attempt_failures.append(f"the browser returned almost nothing ({len(dom)} chars)")
            else:
                for needle, why in REQUIRED:
                    if needle not in dom:
                        attempt_failures.append(f"{why} (expected {needle!r} in the rendered DOM)")
                for needle, why in FORBIDDEN:
                    if needle in dom:
                        attempt_failures.append(f"{why} ({needle!r} was still on the page)")
            if not attempt_failures:
                print(f"[ok] page initialised in a real browser (budget {budget}ms)")
                return
            print(f"[retry] page not settled at {budget}ms: {attempt_failures[0]}")
        failures.extend(attempt_failures)
    finally:
        server.terminate()
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server.kill()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep-going", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    check_syntax(failures)
    if failures and not args.keep_going:
        print("\n".join(f"[FAIL] {f}" for f in failures))
        return 1
    check_render(failures)

    if failures:
        print()
        for failure in failures:
            print(f"[FAIL] {failure}")
        print("\nThe page is broken in a way no unit test would catch.")
        return 1
    print("\npage check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
