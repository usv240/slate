"""Put the board into the state a judge should first see.

Contractual dates are absolute, so a board seeded on Monday shows expired
contracts by Thursday. The deployment now handles that itself: `slate_app/fixtures.py`
rolls the three board fixtures forward as they approach their dates, so a judge
opening the page weeks after submission does not find a dead board.

This script is still the way to get a clean slate deliberately, which is what
you want before recording: it removes everything, including deliveries left by
other visitors, and runs each title once so the board opens with real
measurements rather than an empty shell.

The script removes existing deliveries, and the Grafana alert rule provisioned
with each, then creates three healthy titles with day-scale windows and runs
each once, so the board opens green with real measurements and live metrics
rather than an empty shell.

    python scripts/seed_board.py
    python scripts/seed_board.py --url http://localhost:8080 --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

DEFAULT_URL = "https://slate-delivery-slo-109051079423.us-central1.run.app"

LADDER = [
    {"name": "proxy", "width": 320, "height": 180, "video_codec": "libx264", "video_bitrate_kbps": 300},
    {"name": "review", "width": 640, "height": 360, "video_codec": "libx264", "video_bitrate_kbps": 800},
]

TITLES = [
    ("Nightfall S1E4 streamer package", 52, "priority"),
    ("Harbour Lights feature master", 26, "premiere"),
    ("Salt Road documentary trailer", 9, "standard"),
]


def call(url: str, method: str = "GET", body: dict | None = None, timeout: int = 180):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("content-type", "application/json")
    if data is None and method == "POST":
        request.add_header("content-length", "0")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return response.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as error:
        return error.code, {"error": error.read().decode("utf-8", "replace")[:400]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    base = args.url.rstrip("/")

    status, listing = call(f"{base}/v1/deliveries")
    if status != 200:
        print(f"could not read the board: HTTP {status}")
        return 1
    existing = listing.get("data", [])
    now = datetime.now(timezone.utc)

    print(f"board has {len(existing)} deliveries")
    for record in existing:
        contract = record["contractual_date"]
        expired = datetime.fromisoformat(contract.replace("Z", "+00:00")) < now
        print(f"  {record['title'][:44]:46} {record['status']:10} {'EXPIRED' if expired else 'live'}")

    if args.dry_run:
        print("\ndry run: nothing changed")
        return 0

    for record in existing:
        code, _ = call(f"{base}/v1/deliveries/{record['delivery_id']}", method="DELETE")
        print(f"removed {record['delivery_id']} -> {code}")

    for title, hours, tier in TITLES:
        contract = (now + timedelta(hours=hours)).replace(microsecond=0)
        code, created = call(
            f"{base}/v1/deliveries",
            method="POST",
            body={
                "title": title,
                "contractual_date": contract.isoformat().replace("+00:00", "Z"),
                "penalty_tier": tier,
                "fault_mode": "none",
                "specs": LADDER,
            },
        )
        if code != 201:
            print(f"could not create {title}: HTTP {code} {created}")
            return 1
        delivery_id = created["data"]["delivery_id"]
        rule = bool((created["data"].get("alert_rule") or {}).get("provisioned"))
        run_code, _ = call(f"{base}/v1/deliveries/{delivery_id}/run", method="POST")
        print(f"seeded {title[:40]:42} +{hours}h  alert_rule={rule}  run={run_code}")

    status, listing = call(f"{base}/v1/deliveries")
    rows = listing.get("data", [])
    print(f"\nboard now: {len(rows)} deliveries")
    for record in rows:
        print(f"  {record['title'][:44]:46} {record['status']}")
    unhealthy = [r for r in rows if r["status"] not in {"healthy", "recovered"}]
    if unhealthy:
        print("\nsome deliveries are not green; check the pipeline before recording")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
