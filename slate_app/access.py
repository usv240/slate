"""Optional judge keys and rate limits for the endpoints that cost money.

Two endpoints spend real resources per call: the ADK investigation burns Gemini
tokens across three agents, and the panel reading renders a dashboard and then
sends the PNG to Gemini. Everything else is a read and stays uncapped.

A key is never a gate. Anonymous callers get a working allowance; a key issued
with one click raises it. The key is a stateless HMAC over its own claims, so
there is no account, no database row, and nothing to leak: the server can verify
a key it has never seen before and has no record of who holds one.

Counters are per-process and in memory. With `min-instances 1` and judging-scale
traffic that is accurate enough to be useful and honest enough to describe; it is
not a distributed quota and the product does not claim to be one.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock

KEY_PREFIX = "slate_"
KEY_TTL_SECONDS = 14 * 24 * 3600

#: requests per window, per caller, for the endpoints that spend tokens
ANONYMOUS_QUOTA = 4
KEYED_QUOTA = 20
#: PromQL is a cheap read against our own Prometheus, so it gets a wider bucket
#: than the endpoints that spend Gemini tokens.
PROMQL_QUOTA = 30
WINDOW_SECONDS = 600


def _secret() -> bytes:
    value = os.getenv("SLATE_API_KEY_SECRET")
    if not value:
        # Without a configured secret, keys cannot be issued or verified. The
        # product still works: everyone is simply anonymous.
        raise KeyIssuingDisabled("SLATE_API_KEY_SECRET is not configured")
    return value.encode("utf-8")


class KeyIssuingDisabled(RuntimeError):
    pass


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def issue_key(*, label: str = "judge") -> dict[str, object]:
    """Mint a stateless key. Nothing is stored."""

    claims = {"label": label[:40], "issued_at": int(time.time()), "quota": KEYED_QUOTA}
    payload = _b64(json.dumps(claims, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    signature = _b64(hmac.new(_secret(), payload.encode("ascii"), hashlib.sha256).digest())
    return {
        "api_key": f"{KEY_PREFIX}{payload}.{signature}",
        "quota_per_window": KEYED_QUOTA,
        "window_seconds": WINDOW_SECONDS,
        "expires_in_seconds": KEY_TTL_SECONDS,
        "stored_server_side": False,
        "header": "Authorization: Bearer <api_key>",
    }


def verify_key(api_key: str | None) -> dict[str, object] | None:
    """Return the claims for a valid key, or None. An invalid key is not an error.

    A bad or expired key silently falls back to the anonymous allowance rather
    than rejecting the request, because the key exists to raise a limit and must
    never be able to lock a judge out of the product.
    """

    if not api_key or not api_key.startswith(KEY_PREFIX):
        return None
    body = api_key[len(KEY_PREFIX) :]
    payload, _, signature = body.partition(".")
    if not payload or not signature:
        return None
    try:
        expected = _b64(hmac.new(_secret(), payload.encode("ascii"), hashlib.sha256).digest())
    except KeyIssuingDisabled:
        return None
    if not hmac.compare_digest(expected, signature):
        return None
    try:
        claims = json.loads(_unb64(payload))
    except (ValueError, TypeError):
        return None
    if not isinstance(claims, dict):
        return None
    issued_at = claims.get("issued_at")
    if not isinstance(issued_at, int) or time.time() - issued_at > KEY_TTL_SECONDS:
        return None
    return claims


def bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


@dataclass
class Decision:
    allowed: bool
    quota: int
    remaining: int
    reset_in: int
    keyed: bool


class RateLimiter:
    """Fixed sliding window over the endpoints that spend tokens."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, caller: str, *, quota: int, keyed: bool, now: float | None = None) -> Decision:
        now = now if now is not None else time.time()
        cutoff = now - WINDOW_SECONDS
        with self._lock:
            hits = self._hits[caller]
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= quota:
                reset_in = int(hits[0] + WINDOW_SECONDS - now) + 1
                return Decision(False, quota, 0, max(reset_in, 1), keyed)
            hits.append(now)
            remaining = quota - len(hits)
            reset_in = int(hits[0] + WINDOW_SECONDS - now) + 1
            return Decision(True, quota, remaining, max(reset_in, 1), keyed)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def evaluate(
    *, authorization: str | None, client_ip: str, quota_override: int | None = None
) -> Decision:
    claims = verify_key(bearer_token(authorization))
    if claims:
        quota = quota_override or int(claims.get("quota", KEYED_QUOTA))
        token = bearer_token(authorization)
        return limiter.check(f"key:{client_ip}:{token}", quota=quota, keyed=True)
    quota = quota_override or ANONYMOUS_QUOTA
    return limiter.check(f"ip:{client_ip}", quota=quota, keyed=False)
