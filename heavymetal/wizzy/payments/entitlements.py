"""Entitlements: who may read a full scroll. Signed cookie tokens + payment records with unique tx keys."""

from __future__ import annotations

import base64
import hashlib
import hmac
import sqlite3
import time

SCROLL_COOKIE_PREFIX = "wz_s_"
INNER_COOKIE = "wz_inner"


def sign(wdb, payload: str) -> str:
    body = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    mac = hmac.new(wdb.secret("cookie").encode(), body.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{body}.{mac}"


def verify(wdb, token: str | None) -> str | None:
    if not token or "." not in token:
        return None
    body, mac = token.rsplit(".", 1)
    want = hmac.new(wdb.secret("cookie").encode(), body.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(mac, want):
        return None
    try:
        return base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode()
    except ValueError:
        return None


def _fresh(payload: str | None, kind: str) -> list[str] | None:
    if not payload:
        return None
    parts = payload.split("|")
    if parts[0] != kind or len(parts) < 3:
        return None
    try:
        if float(parts[-1]) < time.time():
            return None
    except ValueError:
        return None
    return parts


def scroll_token(wdb, slug: str, days: int = 30) -> str:
    return sign(wdb, f"s|{slug}|{time.time() + days * 86400:.0f}")


def inner_token(wdb, user_id: int, days: int = 30) -> str:
    return sign(wdb, f"i|{user_id}|{time.time() + days * 86400:.0f}")


def user_token(wdb, user_id: int, minutes: int = 30) -> str:
    """Short-lived link token tying a web checkout to a Telegram user."""
    return sign(wdb, f"u|{user_id}|{time.time() + minutes * 60:.0f}")


def user_from_token(wdb, token: str | None, kind: str = "u") -> int | None:
    parts = _fresh(verify(wdb, token), kind)
    return int(parts[1]) if parts else None


def scroll_access(wdb, cookies: dict, query: dict, slug: str) -> tuple[bool, tuple[str, str] | None]:
    """(allowed, cookie_to_set). Paid scroll cookie, Inner Circle cookie, or an Inner Circle link token (?k=)."""
    parts = _fresh(verify(wdb, cookies.get(SCROLL_COOKIE_PREFIX + slug)), "s")
    if parts and parts[1] == slug:
        return True, None
    uid = user_from_token(wdb, cookies.get(INNER_COOKIE), "i")
    if uid is not None and wdb.tier(uid) == "inner":
        return True, None
    k = query.get("k")
    uid = user_from_token(wdb, k, "i")
    if uid is not None and wdb.tier(uid) == "inner":
        return True, (INNER_COOKIE, k)
    return False, None


def record(
    wdb,
    *,
    user_id: int | None,
    method: str,
    tx_key: str,
    amount: float,
    slug: str | None = None,
    expires_at: float | None = None,
) -> bool:
    """Record a payment. False if this tx key was already used (replay)."""
    try:
        wdb._x(
            "INSERT INTO entitlements(user_id, scroll_slug, method, tx_sig, amount, expires_at, created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (user_id, slug, method, tx_key, amount, expires_at, time.time()),
        )
        return True
    except sqlite3.IntegrityError:
        return False


def grant_inner(
    wdb, user_id: int, *, days: int, method: str, tx_key: str, amount: float, until: float | None = None
) -> bool:
    """Grant (or extend) the Inner Circle. Returns False on a replayed payment."""
    row = wdb.one("SELECT tier, tier_expires_at FROM users WHERE id=?", (user_id,))
    start = max(time.time(), (row["tier_expires_at"] or 0) if row and row["tier"] == "inner" else 0)
    expires = until or start + days * 86400
    if not record(wdb, user_id=user_id, method=method, tx_key=tx_key, amount=amount, expires_at=expires):
        return False
    wdb._x("UPDATE users SET tier='inner', tier_expires_at=? WHERE id=?", (expires, user_id))
    return True


def tx_key_for_header(header: str) -> str:
    return "x402:" + hashlib.sha256(header.encode()).hexdigest()
